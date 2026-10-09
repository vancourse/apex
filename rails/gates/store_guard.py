"""PreToolUse: the rails store, the receipts key and the operator's switches are not the agent's (design R2).

Denies an agent tool call that reads or writes the store's private parts —
snapshot, evidence, receipts key, markers, work.json, state — or names an
operator-only switch (RAILS_OPERATOR, RAILS_SHADOW_ALL, RAILS_GATES_OFF) or the
store-DSN variable a repo's leak.toml names. Reading receipts.jsonl and the
lane logs stays allowed: the agent needs a failing lane's output to fix it.

The `rails` CLI itself writes all of this from its own process, so `rails check`
and friends are never refused here.
"""

from __future__ import annotations

import re
import tomllib

from rails import store
from rails.hookio import Deny, Event

NAME = "store_guard"

_PRIVATE = re.compile(
    r"\.claude[/\\]rails[/\\](?:receipts\.key|[^/\\\s\"']+[/\\](?:snapshot|state\.json|claim_meta\.json|"
    r"[^/\\\s\"']+[/\\](?:evidence|markers|work\.json|pr\.json)))",
    re.IGNORECASE,
)
_SWITCHES = re.compile(
    r"\b(RAILS_OPERATOR|RAILS_SHADOW_ALL|RAILS_GATES_OFF|RAILS_DATA)\b"
)
_RAILS_CLI = re.compile(r"(?:^|[\s;&|])(?:\S*[/\\])?rails(?:\.cmd)?\s")


def _store_env_names(evt: Event) -> list[str]:
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return []
    try:
        cfg = tomllib.loads(
            (repo.top / "rails" / "leak.toml").read_text(encoding="utf-8")
        )
    except (OSError, tomllib.TOMLDecodeError):
        return []
    name = cfg.get("snapshot", {}).get("store_env")
    return [name] if name else []


def _store_names(evt: Event) -> list[str]:
    """Container and database names of the household store, from leak.toml ``[guard] names``.

    Design R2's reference deny: an agent's command that names the real store (``docker exec
    <container> psql``, ``-d <database>``) is refused like its DSN variable is. The names live
    in the repo's leak.toml because only the repo knows them; none means nothing extra is denied.
    """
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return []
    try:
        cfg = tomllib.loads((repo.top / "rails" / "leak.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [str(n) for n in cfg.get("guard", {}).get("names", []) if str(n).strip()]


def check(evt: Event):
    texts = []
    if evt.command:
        texts.append(evt.command)
    texts.extend(evt.paths())
    pattern = evt.tool_input.get("pattern")
    if isinstance(pattern, str):
        texts.append(pattern)
    blob = "\n".join(texts)
    if not blob:
        return None
    if _PRIVATE.search(blob):
        return Deny(
            "rails: the rails store's private files (snapshot, evidence, markers, work.json, state, the receipts key) "
            "are written only by the rails CLI. Use the command that owns the fact: `rails check`, `rails work`, "
            "`rails claim`, `rails post`. Lane logs and receipts.jsonl stay readable."
        )
    m = _SWITCHES.search(evt.command or "")
    if m:
        return Deny(
            f"rails: {m.group(1)} is the operator's switch, set from their own shell; an agent never sets or reads it."
        )
    for name in _store_env_names(evt):
        if name and evt.command and re.search(rf"\b{re.escape(name)}\b", evt.command):
            return Deny(
                f"rails: {name} names the household store. Only `rails snapshot` / `rails oracle`, run by the operator, read it."
            )
    if evt.command and not _RAILS_CLI.search(evt.command):
        for name in _store_names(evt):
            if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", evt.command):
                return Deny(
                    f"rails: `{name}` is the household store (leak.toml [guard] names). Port the question to the "
                    "planted database, or ask the operator to run it; real values never enter an agent's context."
                )
    return None
