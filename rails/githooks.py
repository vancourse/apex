"""Git hooks from the plugin (design R3): push consent replaced by evidence.

``rails adopt`` points ``core.hooksPath`` at ``<rails>/git-hooks`` and records the
previous hooks directory in ``rails.chainHooksPath``. Every hook here does its
own work and then runs the same-named hook from that previous directory with
the same arguments and stdin, so adopting rails never silently disables a
repo's own hooks (the hazard of a single-directory hooks setting).

pre-push refuses, in order:
  * ``hold`` (the operator's word, set from a prompt or ``rails hold``);
  * a ref carrying history the repo rewrote away (``rails history retire``);
  * no check marker for the pushed commit: ``--quick`` while the branch has no
    open PR, the full marker once one exists;
  * the leak check: a value matched (3) or no fresh snapshot (4). Fails closed.
Every pushed ref is judged by its remote ref and sha, whatever the source was
spelled as (``HEAD:x`` and a raw sha used to skip the marker and leak checks).
``RAILS_OPERATOR=1`` from the operator's own shell skips the marker and hold,
never the retired-history or leak check, and is ignored inside an agent's tool call.

Each refusal is a row in hooks/gates.toml (``prepush_marker``, ``prepush_hold``,
``prepush_retired``, ``prepush_leak``); a row in shadow logs ``would-deny`` and
lets the push through.
Commits are never blocked by rails: a commit is the agent's save point.

A crash in this module never blocks: it prints a loud notice and chains on.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rails import store

_ZERO = "0" * 40


def _registry_rows() -> dict:
    from rails.dispatch import load_registry

    try:
        return {row.name: row for row in load_registry()}
    except Exception:  # noqa: BLE001
        return {}


def _shadowed(name: str) -> bool:
    row = _registry_rows().get(name)
    if row is None:
        return False
    return row.shadowed(_dt.date.today())


def _log(repo: store.RepoId, gate: str, verdict: str) -> None:
    try:
        store.append_jsonl(
            repo.dir / "firings.jsonl",
            {
                "ts": int(time.time()),
                "leaf": repo.leaf,
                "event": "git:pre-push",
                "gate": gate,
                "verdict": verdict,
            },
        )
    except OSError:
        pass


def operator() -> bool:
    return (
        os.environ.get("RAILS_OPERATOR") == "1" and os.environ.get("CLAUDECODE") != "1"
    )


def held(repo: store.RepoId) -> str | None:
    state = store.read_json(repo.dir / "state.json", {}) or {}
    hold = state.get("hold")
    if isinstance(hold, dict) and hold.get("on"):
        return str(hold.get("since", "?"))
    return None


def open_pr(repo: store.RepoId, branch: str) -> bool:
    pr = store.read_json(repo.leaf_dir / "pr.json", None)
    if (
        isinstance(pr, dict)
        and pr.get("number")
        and pr.get("state", "OPEN") == "OPEN"
        and pr.get("branch") in (None, branch)
    ):
        return True
    if not shutil.which("gh") or not branch:
        return False
    try:
        done = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "state"],
            cwd=str(repo.top),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if done.returncode != 0:
        return False
    try:
        return json.loads(done.stdout).get("state") == "OPEN"
    except ValueError:
        return False


def pre_push(
    argv: list[str], ref_lines: list[str], repo: store.RepoId
) -> tuple[int, list[str]]:
    """(exit code, messages). Exit 1 refuses the push."""
    from rails import leak, receipts

    messages: list[str] = []
    refuse = False
    is_operator = operator()

    def refusal(gate: str, text: str) -> None:
        nonlocal refuse
        if _shadowed(gate):
            _log(repo, gate, "would-deny")
            messages.append(
                f"[rails shadow: {gate} would refuse] {text.splitlines()[0]}"
            )
        else:
            _log(repo, gate, "deny")
            messages.append(text)
            refuse = True

    if not is_operator:
        since = held(repo)
        if since:
            refusal(
                "prepush_hold",
                f"rails: refused - the operator said `hold` ({since}). They lift it with `release`.",
            )
    retired_refusals(repo, ref_lines, refusal)
    # Judge by what lands on the remote: `git push origin HEAD:x` and a raw sha hand the
    # hook "HEAD" / the sha as the local ref, and both used to skip every check below.
    sending = [
        line for line in ref_lines if len(line.split()) == 4 and line.split()[1] != _ZERO
    ]
    pushes = []
    for line in sending:
        parts = line.split()
        if parts[2].startswith("refs/heads/"):
            pushes.append((parts[2].removeprefix("refs/heads/"), parts[1]))
    if pushes and not is_operator:
        intent_refusal(repo, refusal)
    if not is_operator:
        for branch, sha in pushes:
            full = open_pr(repo, branch)
            if not receipts.has_marker(repo, sha, full=full):
                need = "rails check" if full else "rails check --quick"
                refusal(
                    "prepush_marker",
                    f"rails: refused - no {'full' if full else 'quick'} check marker for {sha[:12]} ({branch}).\n"
                    f"  run `{need}` on this commit, then push again (it never blocks a commit).",
                )
    if sending:
        from rails.check import find_lanes_file
        from rails import lanes as lanes_mod

        lanes_file = find_lanes_file(repo.top)
        base = lanes_mod.load(lanes_file).base if lanes_file else "origin/main"
        result = leak.check_lines(
            repo,
            leak.pushed_lines(repo.top, ref_lines, base),
            leak.allowlist_for(repo.top),
        )
        if result.code != leak.EXIT_CLEAN:
            refusal("prepush_leak", "rails: refused - " + result.report())
    return (1 if refuse else 0), messages


def intent_refusal(repo: store.RepoId, refusal) -> None:
    """`prepush_intent`: an agent pushes only work whose intent the operator saw and acked (R24).

    The intent is ``.rails/intent.md``; it is acked when the operator's next message after a
    turn that SHOWED it (its ``intent:<hash>`` marker in the final message) did not change
    what is built. A push from the operator's own shell is not an agent's and is not asked.
    """
    from rails import intent
    from rails.gitutil import in_agent

    if not in_agent():
        return
    try:
        h = intent.current_hash(repo.top)
        acked = intent.acked(repo, repo.top) if h else False
    except Exception as exc:  # noqa: BLE001 - fail closed here, not open in main()
        refusal("prepush_intent", f"rails: refused - the intent could not be read ({type(exc).__name__})")
        return
    if h is None:
        refusal(
            "prepush_intent",
            "rails: refused - no intent for this work. Write .rails/intent.md (`rails template intent`), "
            "end the turn SHOWING it with its intent:<hash> line, and push after the operator's next message.",
        )
    elif not acked:
        refusal(
            "prepush_intent",
            f"rails: refused - intent {h} has not been acked. End the turn showing it (its line "
            f"`{intent.marker(h)}` in your final message); the operator's next message acks it.",
        )


def retired_refusals(repo: store.RepoId, ref_lines: list[str], refusal) -> None:
    """`prepush_retired`: no ref may carry history the repo rewrote away.

    Runs for the operator too (it guards data, like the leak check), and fails closed
    when the repo has retired a tip but the check cannot run: a crash here must not
    fall through to main()'s fail-open handler.
    """
    from rails import history

    try:
        retired = history.load(repo.top)
        if retired is None:
            return
        for line in ref_lines:
            why = history.refusal(retired, line)
            if why:
                refusal("prepush_retired", why)
    except Exception as exc:  # noqa: BLE001
        refusal(
            "prepush_retired",
            f"rails: refused - the retired-history check crashed ({type(exc).__name__}: {exc}); "
            "it fails closed because this repo has retired history",
        )


# --- chaining -----------------------------------------------------------------


def chained_dir(top: Path) -> Path | None:
    out = subprocess.run(
        ["git", "-C", str(top), "config", "--get", "rails.chainHooksPath"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if out:
        path = Path(out)
        return path if path.is_absolute() else (top / path)
    common = subprocess.run(
        ["git", "-C", str(top), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not common:
        return None
    common_path = Path(common) if Path(common).is_absolute() else (top / common)
    return common_path / "hooks"


def run_chained(name: str, argv: list[str], stdin_text: str, top: Path) -> int:
    folder = chained_dir(top)
    if folder is None:
        return 0
    hook = folder / name
    rails_hooks = Path(__file__).resolve().parent.parent / "git-hooks"
    try:
        if hook.resolve().parent == rails_hooks.resolve():
            return 0  # never chain into ourselves
    except OSError:
        pass
    if not hook.is_file():
        return 0
    shell = shutil.which("sh") or shutil.which("bash")
    cmd = [shell, str(hook), *argv] if shell else [str(hook), *argv]
    return subprocess.run(cmd, cwd=str(top), input=stdin_text, text=True).returncode


def main(argv: list[str]) -> int:
    name = argv[1] if len(argv) > 1 else ""
    args = argv[2:]
    stdin_text = (
        sys.stdin.read()
        if name in ("pre-push", "pre-receive", "post-rewrite", "reference-transaction")
        else ""
    )
    top = Path.cwd()
    repo = store.find_repo(top)
    if repo is not None and name == "pre-push":
        try:
            code, messages = pre_push(args, stdin_text.splitlines(), repo)
        except Exception as exc:  # noqa: BLE001 — a broken hook must not wedge every push
            code, messages = (
                0,
                [
                    f"RAILS: pre-push crashed ({type(exc).__name__}: {exc}); NOT CHECKED, chaining on"
                ],
            )
        for message in messages:
            print(message, file=sys.stderr)
        if code != 0:
            return code
    return run_chained(name, args, stdin_text, repo.top if repo else top)
