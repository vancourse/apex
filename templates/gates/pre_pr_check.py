#!/usr/bin/env python3
"""Run what CI would run for this diff, locally, before opening the PR.

The problem this answers: by the time CI reports red, a catch-up cycle has already
started — push, wait ~2 minutes, read the log, fix, push again. Running the same
gates locally first, in the same order CI reports them (cheapest first), turns most
of that into an edit-run loop measured in seconds. The one thing left for CI to
prove is "does this same code behave the same way on a clean checkout" — which a
local run cannot prove and should not pretend to.

**Reuse the CI jobs' own commands; never restate them.** This is the single rule
that keeps the tool honest. If this file said `ruff check src/` while the workflow
said `ruff check .`, then "pre-PR passed" and "CI passed" would quietly become two
different definitions of green, and the local run would be worse than nothing —
it would be a green light that means something else. So each step below is the
*same argv* as the job it mirrors, and `build_steps` only builds a step when the
repository actually shows the config that job reads. When you install this file,
open `build_steps` and reconcile it against your workflow line by line; that
reconciliation is the whole product, not an implementation detail of it.

Ordered cheapest-to-most-expensive so a broken run fails in seconds, not minutes:
format, then lint, then lockfile, then types, then the (potentially narrowed) test
suite. Each step's own failure output is a syntax the developer already knows — this
gate reprints nothing, it only decides whether to keep going.

Ahead of all of those sits ``preflight``, two pure-git checks that ask whether the
branch is the shape its author believes it is. They live here rather than in CI
because **CI cannot see either problem**, and both cost milliseconds:

* **base** — a commit whose subject ends in ``(#123)`` was written by the forge's
  squash-merge, never by hand, so such a commit belongs to the default branch's
  history by construction. One sitting in ``origin/<default>..HEAD`` therefore means
  the branch was cut from a base the default branch has since **rewritten**: the
  commit's content is still here under a sha the default branch no longer has, while
  the default branch carries a re-landed edition of the same work. Nothing about
  this is broken, which is exactly why it is invisible — the merge is legitimate,
  the forge reports the PR mergeable, and the tests pass. It just lands two editions
  of someone else's change. See ``inherited_commits``.
* **scope** — the declaration is the conventional-commit type the author already
  wrote, so there is no second place to keep in sync and no new metadata to forget.
  If every commit on the branch is ``docs(...)``, the diff has to be prose; source
  files in it mean the branch picked up something it did not mean to. See
  ``declares_docs_only``.

Usage::

    python ci/pre_pr_check.py                     # diff against the default branch
    python ci/pre_pr_check.py --base some/branch   # diff against another ref
    python ci/pre_pr_check.py --skip-tests         # gates only, no test suite

Honest limit: this runs when the developer runs it. A branch that never sees it is
unguarded, and no amount of documentation changes that — only the CI job binds
everyone.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import time


def repo_root() -> pathlib.Path:
    """The repository root — git's answer when git can give one.

    The fallback assumes this file was installed one directory below the root (the
    suggested home is `ci/`), so the tool still resolves in a checkout where git is
    unavailable.
    """
    here = pathlib.Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "-C", str(here), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return pathlib.Path(result.stdout.strip())
    except OSError:
        pass
    return here.parent


REPO_ROOT = repo_root()

# --------------------------------------------------------------------- edit me
#: An env var the test step needs before it can pass — a database URL, a service
#: token, a fixture path. None means the suite is self-contained. A step that would
#: fail for a missing dependency is reported as SKIPPED with the reason, because a
#: red run the developer cannot act on teaches them to stop running the tool.
TEST_ENV: str | None = None

#: Optional: a script that reads changed paths on stdin and prints the test paths
#: to run, so the local suite is scoped exactly the way CI scopes it. Absent or
#: failing, the full suite runs — the same safe default a selector uses for a path
#: it has no mapping for.
#:
#: **That default is safe only where reachability is genuinely unknown.** A selector
#: that answers "run everything" for a path it does not *recognize* is charging every
#: developer the full suite for the privilege of its own missing mapping. Before
#: accepting the fallback for a path, ask whether that path can *provably* not reach
#: the rest: a frontend file cannot reach a backend package, and a docs file reaches
#: nothing. Where the answer is provable, encode it — those are the mappings worth
#: writing first, because they are the ones that turn a four-minute wait into zero.
#:
#: The measured shape of getting this wrong: a ~6,300-test suite run locally six times
#: in one session at ~4 minutes each — ~25 minutes of waiting, most of it re-proving
#: what CI proves on push. A gate that expensive stops being run, and then none of the
#: cheaper gates above it run either. See `apex:pr-discipline` §2 for the rule this
#: implements.
TEST_SELECTOR = pathlib.Path("ci") / "select_tests.py"
# -----------------------------------------------------------------------------

# A subject ending in "(#123)" is written by the forge's squash-merge, never by
# hand — so such a commit belongs to the default branch's history by construction.
# See `inherited_commits` for what it means to find one on a feature branch.
MERGED_PR_SUBJECT = re.compile(r"\(#\d+\)$")

# Conventional-commit type, e.g. "docs(adr): ..." or "feat!: ...".
COMMIT_TYPE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?!?:")

# Types whose name is a promise that the change is prose only.
DOC_ONLY_TYPES = frozenset({"docs", "design"})


class Step:
    def __init__(self, name: str, argv: list[str], *, requires_env: str | None = None):
        self.name = name
        self.argv = argv
        self.requires_env = requires_env


def default_base() -> str:
    """``origin/<default branch>``, read from the remote rather than assumed.

    ``origin/HEAD`` is a symbolic ref the clone sets from the remote's own default,
    so it is the only answer that does not hardcode somebody else's branch name.
    A repository whose ``origin/HEAD`` was never set (added as a remote by hand, or
    a fetch that predates it) falls back to whichever conventional name resolves.
    """
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "origin/main"
    ref = result.stdout.strip()
    if result.returncode == 0 and ref.startswith("refs/remotes/"):
        return ref[len("refs/remotes/") :]

    for name in ("main", "master", "trunk", "develop"):
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"origin/{name}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return f"origin/{name}"
    return "origin/main"


def changed_files(base: str) -> list[str]:
    """The same diff CI computes: against the merge base, not the tip.

    Using the merge base (``base...HEAD`` with three dots) rather than the tip
    matters here for the same reason it matters in CI: it means the check reflects
    only *this branch's* changes, not "everything the default branch has done since
    I last synced" — so it stays narrow even right after a catch-up merge.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"could not diff against '{base}': {result.stderr.strip()}", file=sys.stderr
        )
        print("falling back to the full suite for the test step", file=sys.stderr)
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def branch_commits(base: str) -> list[tuple[str, str]]:
    """The commits this branch has that ``base`` does not, as ``(sha, subject)``.

    Two dots, not three: the question is "what commits are on HEAD and not on base",
    which is exactly what ``base..HEAD`` answers. (``changed_files`` uses three dots
    because it asks a different question — what this branch *changed* relative to
    the fork point.)

    Returns an empty list if the ref cannot be resolved, matching ``changed_files``:
    an unusable base makes the preflight checks silent rather than making the whole
    tool unusable.
    """
    result = subprocess.run(
        ["git", "log", "--format=%h\x1f%s", f"{base}..HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    commits = []
    for line in result.stdout.splitlines():
        sha, _, subject = line.partition("\x1f")
        if sha.strip():
            commits.append((sha.strip(), subject.strip()))
    return commits


def inherited_commits(commits: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Commits that look like the default branch's, found where only yours should be.

    A ``(#123)`` suffix is applied by the forge's squash-merge, so a commit wearing
    one is a commit that already landed on the default branch. Finding one in
    ``origin/<default>..HEAD`` therefore means the branch was cut from a base that
    the default branch has since **rewritten** — the commit's content is still here
    under a sha the default branch no longer has, while the default branch carries a
    re-landed edition of the same work.

    That is not a merge conflict and the forge will not flag it: the merge is
    legitimate and reports as mergeable, the diff applies, the tests pass. It simply
    mixes two editions of the same change, and the second edition is the one nobody
    reviewed. The branch that motivated this check sat in exactly that state —
    fifteen commits, of which one was an inherited squash-merge dragging 48 unrelated
    files into what was meant to be a five-file docs branch.

    Measured across one repository's 34 local branches when this landed: three fired,
    all three genuinely poisoned, no false positives.
    """
    return [
        (sha, subject) for sha, subject in commits if MERGED_PR_SUBJECT.search(subject)
    ]


def declares_docs_only(commits: list[tuple[str, str]]) -> bool:
    """True when every commit's own conventional-commit type promises prose.

    The scope declaration is the commit type the author already wrote — there is no
    second place to keep it in sync, and no new metadata to forget. A subject with no
    parseable type is treated as *not* a docs promise, so an unlabelled commit widens
    the allowed scope rather than narrowing it: the check should fire on a broken
    promise, never on a missing one.

    Empty input is not a promise either — a branch with no commits has declared
    nothing.
    """
    if not commits:
        return False
    types = [COMMIT_TYPE.match(subject) for _, subject in commits]
    return all(m is not None and m.group("type") in DOC_ONLY_TYPES for m in types)


def non_doc_paths(paths: list[str]) -> list[str]:
    """The changed paths a docs-only branch has no business touching."""
    return [p for p in paths if not (p.startswith("docs/") or p.endswith(".md"))]


def preflight(base: str) -> list[str]:
    """Two git-only checks, run before anything that costs money.

    Both answer the same question from different sides — "is this branch what its
    author thinks it is?" — and both are near-free, so they precede the linters.
    Returns the names of the checks that failed.
    """
    failures = []
    commits = branch_commits(base)

    print("-- base (git history) --")
    inherited = inherited_commits(commits)
    if inherited:
        print(
            "   commits carrying a merged-PR number, which only the base branch's do:"
        )
        for sha, subject in inherited:
            print(f"     {sha} {subject}")
        print(
            f"   This branch was cut from a base that {base} has since rewritten.\n"
            f"   Merging it would mix two editions of that work — and it will\n"
            f"   report as mergeable, because as far as git is concerned it is.\n"
            f"   Fix: re-cut from {base} and cherry-pick your own commits onto it."
        )
        print("-- base (git history): FAIL --\n")
        failures.append("base (git history)")
    else:
        print("-- base (git history): PASS --\n")

    print("-- scope --")
    # An inherited commit is the base branch's, not the author's, so it does not get
    # to widen the scope this branch declared. This is what lets the two checks
    # compose: without it a single foreign `feat(...)` commit would silently license
    # every source path it dragged in.
    own = [c for c in commits if c not in inherited]
    strays = non_doc_paths(changed_files(base)) if declares_docs_only(own) else []
    if strays:
        print("   every commit here declares a docs type, but the diff is not prose:")
        for path in strays:
            print(f"     {path}")
        print(
            "   Either the branch picked up files it did not mean to, or one of\n"
            "   these changes needs its own non-docs commit to declare it."
        )
        print("-- scope: FAIL --\n")
        failures.append("scope")
    else:
        print("-- scope: PASS --\n")

    return failures


def run(step: Step) -> bool:
    if step.requires_env and not os.environ.get(step.requires_env):
        print(f"-- {step.name}: SKIPPED ({step.requires_env} not set) --")
        return True
    print(f"-- {step.name} --")
    started = time.monotonic()
    try:
        result = subprocess.run(step.argv, cwd=REPO_ROOT)
        ok = result.returncode == 0
    except OSError as exc:
        # The tool this step mirrors is not installed here. That is a broken local
        # setup, not a broken branch, and saying which is the difference between a
        # developer fixing it and a developer distrusting the gate.
        print(f"   cannot run {step.argv[0]!r}: {exc}")
        ok = False
    elapsed = time.monotonic() - started
    print(f"-- {step.name}: {'PASS' if ok else 'FAIL'} ({elapsed:.1f}s) --\n")
    return ok


def _pyproject(root: pathlib.Path) -> str:
    path = root / "pyproject.toml"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _runner(root: pathlib.Path) -> list[str]:
    """The prefix that puts the repo's own environment in front of a tool.

    Derived from the lockfile the repo actually keeps, so the local run resolves the
    same pinned versions CI resolves instead of whatever happens to be on PATH.
    """
    if (root / "uv.lock").is_file():
        return ["uv", "run"]
    if (root / "poetry.lock").is_file():
        return ["poetry", "run"]
    return []


def build_steps(base: str, skip_tests: bool) -> list[Step]:
    """The gate list for this repository, cheapest first.

    Every step is conditional on a config file the matching CI job reads. A repo with
    no ruff config gets no ruff step rather than a spurious failure — the same
    false-positive argument the PR-body gate makes: a gate that fires on correct work
    gets routed around, and then none of the gates run.
    """
    root = REPO_ROOT
    runner = _runner(root)
    pyproject = _pyproject(root)
    steps: list[Step] = []

    ruff_configured = (
        "[tool.ruff]" in pyproject
        or (root / "ruff.toml").is_file()
        or (root / ".ruff.toml").is_file()
    )
    if ruff_configured:
        steps.append(Step("format (ruff)", [*runner, "ruff", "format", "--check", "."]))
        steps.append(Step("lint (ruff)", [*runner, "ruff", "check", "."]))

    if (root / "uv.lock").is_file():
        steps.append(Step("lockfile", ["uv", "lock", "--check"]))

    if "[tool.pyright]" in pyproject or (root / "pyrightconfig.json").is_file():
        steps.append(Step("types (pyright)", [*runner, "pyright"]))
    elif "[tool.mypy]" in pyproject or (root / "mypy.ini").is_file():
        steps.append(Step("types (mypy)", [*runner, "mypy", "."]))

    if not skip_tests:
        steps.append(Step("tests", _test_argv(base, runner), requires_env=TEST_ENV))

    return steps


def _test_argv(base: str, runner: list[str]) -> list[str]:
    """The test command, narrowed by the CI selector when the repo ships one."""
    selector = REPO_ROOT / TEST_SELECTOR
    if not selector.is_file():
        print("-- test scope: full suite (no test selector installed) --")
        return [*runner, "pytest", "-q"]

    select = subprocess.run(
        [sys.executable, str(selector)],
        input="\n".join(changed_files(base)),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    paths = [line for line in select.stdout.splitlines() if line.strip()]
    reason = select.stderr.strip()
    if paths and paths != ["ALL"]:
        print(f"-- test scope: {reason} --")
        return [*runner, "pytest", "-q", *paths]
    print(f"-- test scope: full suite ({reason or 'no changed files detected'}) --")
    return [*runner, "pytest", "-q"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=None,
        help="ref to diff against (default: the remote's own default branch)",
    )
    parser.add_argument(
        "--skip-tests", action="store_true", help="run only the non-test gates"
    )
    args = parser.parse_args(argv)
    base = args.base or default_base()

    if TEST_ENV and not os.environ.get(TEST_ENV) and not args.skip_tests:
        print(
            f"note: {TEST_ENV} is not set; the test step will be skipped.\n",
            file=sys.stderr,
        )

    # Aborting rather than accumulating: if the branch is cut from the wrong base,
    # every gate below this line is reporting on a tree that is not the one that
    # would land, so a green run underneath a failed preflight would be worse than
    # no run at all.
    preflight_failures = preflight(base)
    if preflight_failures:
        print(f"FAILED: {', '.join(preflight_failures)}")
        print("later gates were not run — they would describe the wrong tree")
        return 1

    steps = build_steps(base, args.skip_tests)
    if not steps:
        print(
            "no gates were built for this repository — reconcile build_steps() "
            "against your CI workflow, or this tool proves nothing"
        )
        return 0
    failed = [step.name for step in steps if not run(step)]

    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print("all gates passed locally; CI should agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
