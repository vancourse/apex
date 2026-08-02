#!/usr/bin/env python3
"""Blocking CI check: a PR body must carry the sections its own diff calls for.

This is the piece an advisory hook cannot be. A Claude Code hook fires only inside
a Claude Code session, and GitHub applies `.github/pull_request_template.md` only in
its web UI — `gh pr create --body-file` skips it, and so does every agent and every
CLI user. Until a check runs server-side, nothing ever reads what a PR body actually
says.

**Requirements are derived from the diff, never fixed.**

    the diff                          the sections it must carry
    --------------------------------  ---------------------------------
    any                               What this does · Why this shape
    changes shipped source            + Test plan · Wiring
    ADDS shipped source               + Reuse verdict
    touches a custody/trust path      + Risk note

That derivation is the load-bearing design decision, and the argument for it is
about false positives, not completeness. A gate demanding every section of every PR
fails on a typo fix. A gate that fires on correct work teaches people to reach for
`gh pr merge --admin` — which skips every *other* required check too, so a single
false positive here costs far more than the gate was ever worth. Requiring only what
the diff implies is what keeps the check survivable, and survivable is the only kind
of check that stays turned on.

The `Reuse verdict` rule is the server-side half of the reuse question: an authoring
hook can *ask* whether an existing primitive was checked, and cannot enforce the
answer. This refuses the merge.

**A heading alone is not a section.** Content identical to the template's own
placeholder counts as absent, because pasting the skeleton back is the obvious way
to satisfy a section checker without answering it.

Sensitive paths are configuration, not code
-------------------------------------------
Which trees carry custody or trust is a per-repository fact, so this script reads
them rather than shipping a guess. It looks for a `[tool.apex]` table in
`pyproject.toml` first, then for a `.apex.toml` at the repository root, and reads
two keys — both optional, both lists of strings:

    # pyproject.toml
    [tool.apex]
    sensitive_path_prefixes = [
        "auth/",                 # anything that decides who you are
        "secrets/",              # anything that holds what proves it
        "crypto/",               # anything that signs, seals, or verifies
        "billing/",              # anything that moves money
        "deploy/",               # anything that changes what runs in production
        ".github/workflows/",    # anything that changes what CI is allowed to do
    ]
    sensitive_path_substrings = ["migration", "credential", "webauthn"]

    # or .apex.toml at the repository root — bare keys, no table header needed
    sensitive_path_prefixes = ["auth/", "secrets/"]
    sensitive_path_substrings = ["migration"]

Prefixes match the start of a repo-relative path; substrings match anywhere in it,
case-insensitively, which is how a `migrations/` directory buried three levels down
still counts. Enumerate them rather than pattern-matching: the list is then
reviewable in a diff, and a new sensitive area becomes a deliberate addition.

**Fail-soft is deliberate.** If neither file declares the keys, both lists are empty,
`is_sensitive` is always False, and the Risk-note requirement simply never fires —
the other three rules still do. That is the intended behaviour for an unconfigured
repository. The alternative, guessing which paths are sensitive, would fire on
correct work in a repository the gate knows nothing about, and that is precisely the
false positive the derivation above exists to avoid.

Usage — `git diff --name-status` on stdin::

    git diff --name-status "$BASE_SHA...$HEAD_SHA" \
      | PR_BODY="$BODY" PR_AUTHOR_TYPE="$AUTHOR_TYPE" python ci/pr_body_check.py

Exit 0 when satisfied, 1 when not, with a `::error::` annotation per finding.

Honest limit: `gh pr merge --admin` bypasses every required check, this one included.
Repository admins can always override branch protection; that is the forge's model,
not a hole here. What this removes is the *silent* path — skipping the template now
takes a deliberate, logged act rather than a `--body-file` nobody notices.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass

try:  # tomllib is stdlib from Python 3.11; older runners get the empty config.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - depends on the runner's Python
    tomllib = None  # type: ignore[assignment]


def repo_root() -> pathlib.Path:
    """The repository root — git's answer when git can give one.

    The fallback assumes this file was installed one directory below the root (the
    suggested home is `ci/`), which is what makes the script work in a checkout with
    no git available, such as a container that only unpacked an archive.
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
TEMPLATE = REPO_ROOT / ".github" / "pull_request_template.md"

#: An explicit, reasoned opt-out. A gate with no escape hatch gets bypassed with
#: `--admin` instead, which skips every other check too — a far worse outcome. The
#: reason is mandatory, and it is echoed into the job log so the skip stays visible.
SKIP = re.compile(
    r"<!--\s*pr-body-check:\s*skip(?P<reason>.*?)-->", re.IGNORECASE | re.DOTALL
)
#: A reason must be words, not punctuation. A first cut of this pattern accepted
#: `<!-- pr-body-check: skip -->` by matching the separator itself as the "reason" —
#: an escape hatch that recorded nothing, which is no accountability at all.
MIN_REASON_WORDS = 2


def stated_reason(body: str) -> str | None:
    """The skip marker's reason, or None when absent or too thin to be one."""
    marker = SKIP.search(body)
    if marker is None:
        return None
    reason = marker.group("reason").strip(" \t\r\n-—:*")
    return reason if len(reason.split()) >= MIN_REASON_WORDS else None


ALWAYS = ("What this does", "Why this shape")
FOR_SOURCE = ("Test plan", "Wiring")
FOR_NEW_SOURCE = ("Reuse verdict",)
FOR_SENSITIVE = ("Risk note",)

#: Ordinary constants, not configuration — this file is installed into your repo, so
#: edit them here if your tree ships a language these miss.
SOURCE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".rb",
    ".cs",
    ".php",
    ".swift",
    ".scala",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
}
TEST_MARKERS = (
    "tests/",
    "__tests__/",
    "test_",
    "_test.",
    ".test.",
    ".spec.",
    "conftest",
)


def _read_toml(path: pathlib.Path) -> dict:
    """A parsed TOML file, or {} for anything unreadable.

    A malformed `pyproject.toml` is somebody else's failure to report; this check
    refusing to run over it would only add noise to a build that is already red.
    """
    if tomllib is None or not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, ValueError):
        return {}


def apex_config(root: pathlib.Path) -> dict:
    """The repo's `[tool.apex]` settings — pyproject first, then `.apex.toml`."""
    pyproject = _read_toml(root / "pyproject.toml")
    table = pyproject.get("tool", {}).get("apex")
    if isinstance(table, dict) and table:
        return table

    dedicated = _read_toml(root / ".apex.toml")
    nested = dedicated.get("tool", {}).get("apex")
    # A dedicated file may use bare keys or mirror pyproject's table header, so a
    # block copied out of pyproject.toml keeps working when it is moved here.
    if isinstance(nested, dict) and nested:
        return nested
    return dedicated


def _string_list(value: object) -> tuple[str, ...]:
    """The strings in a TOML list, ignoring anything that is not one."""
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def sensitive_patterns(root: pathlib.Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(prefixes, substrings)` from config — `((), ())` when nothing declares them."""
    table = apex_config(root)
    return (
        _string_list(table.get("sensitive_path_prefixes")),
        tuple(s.lower() for s in _string_list(table.get("sensitive_path_substrings"))),
    )


SENSITIVE_PREFIXES, SENSITIVE_SUBSTRINGS = sensitive_patterns(REPO_ROOT)


@dataclass(frozen=True)
class Finding:
    section: str
    reason: str
    problem: str

    def annotation(self) -> str:
        return (
            f"::error::PR body — '{self.section}' is {self.problem}. "
            f"Required because {self.reason}."
        )


def sections(markdown: str) -> dict[str, str]:
    """Normalised heading -> the body beneath it."""
    found: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current is not None:
            found[current] = "\n".join(buffer).strip()

    for line in markdown.splitlines():
        if line.strip().startswith("#"):
            flush()
            current = line.strip().lstrip("#").strip().rstrip(":").lower()
            buffer = []
        elif current is not None:
            buffer.append(line)
    flush()
    return found


def _meaningful(content: str) -> str:
    """Content with the template's guidance removed — comments and empty table rows."""
    stripped = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    kept = [
        line
        for line in stripped.splitlines()
        # A row of only pipes, dashes and spaces is table scaffolding, not an answer.
        if line.strip() and set(line.strip()) - set("|-: ")
    ]
    return re.sub(r"\s+", " ", " ".join(kept)).strip().lower()


def is_answered(content: str, placeholder: str) -> bool:
    """True when the section says something the template did not already say."""
    answer = _meaningful(content)
    return bool(answer) and answer != _meaningful(placeholder)


def changed_paths(stdin_lines: list[str]) -> tuple[list[str], list[str]]:
    """`git diff --name-status` output -> (all paths, added paths)."""
    every: list[str] = []
    added: list[str] = []
    for raw in stdin_lines:
        parts = [p for p in raw.rstrip("\n").split("\t") if p]
        if len(parts) < 2:
            continue
        status, path = parts[0].strip(), parts[-1].strip()
        if not path:
            continue
        every.append(path)
        # Renames arrive as R100 with the destination last; that is a new path.
        if status.startswith(("A", "R")):
            added.append(path)
    return every, added


def is_shipped_source(path: str) -> bool:
    if pathlib.PurePosixPath(path).suffix not in SOURCE_SUFFIXES:
        return False
    return not any(marker in path for marker in TEST_MARKERS)


def is_sensitive(path: str) -> bool:
    """True when config says this path carries custody or trust.

    With no config, both tuples are empty and this is always False — see the module
    docstring on why an unconfigured repo gets silence rather than a guess.
    """
    lowered = path.lower()
    return path.startswith(SENSITIVE_PREFIXES) or any(
        s in lowered for s in SENSITIVE_SUBSTRINGS
    )


def required_sections(every: list[str], added: list[str]) -> dict[str, str]:
    """Section -> why this diff demands it. Empty when the diff demands nothing."""
    if not every:
        return {}
    needed = {name: "every PR" for name in ALWAYS}

    source = [p for p in every if is_shipped_source(p)]
    if source:
        for name in FOR_SOURCE:
            needed[name] = f"the diff changes shipped source ({source[0]})"

    new_source = [p for p in added if is_shipped_source(p)]
    if new_source:
        for name in FOR_NEW_SOURCE:
            needed[name] = f"the diff ADDS shipped source ({new_source[0]})"

    sensitive = [p for p in every if is_sensitive(p)]
    if sensitive:
        for name in FOR_SENSITIVE:
            needed[name] = f"the diff touches a custody/trust path ({sensitive[0]})"
    return needed


def check(
    body: str, every: list[str], added: list[str], template: str = ""
) -> list[Finding]:
    """Findings against the body. Empty means it carries what the diff calls for."""
    wanted = required_sections(every, added)
    skeleton = sections(template)
    present = sections(body)

    findings: list[Finding] = []
    for name, reason in wanted.items():
        key = name.lower()
        if key not in present:
            findings.append(Finding(name, reason, "absent"))
        elif not is_answered(present[key], skeleton.get(key, "")):
            findings.append(
                Finding(name, reason, "present but still the template's placeholder")
            )
    return findings


def main() -> int:
    body = os.environ.get("PR_BODY") or ""

    if os.environ.get("PR_AUTHOR_TYPE", "User").lower() == "bot":
        print("author is a bot — PR-body conventions do not apply; skipping")
        return 0

    reason = stated_reason(body)
    if reason:
        print(f"::notice::pr-body-check skipped by marker: {reason}")
        return 0
    if SKIP.search(body):
        # A marker with no usable reason is simply not a skip, and the body is
        # checked normally. This is a `notice`, not an `error`, because prose that
        # merely *documents* the marker matches too — this file's own help text
        # spells it out, and a PR describing the escape hatch would otherwise carry
        # an error annotation on an otherwise passing check. Mentioning a thing is
        # not invoking it.
        print(
            "::notice::a pr-body-check skip marker was seen but states no reason; ignoring it"
        )

    every, added = changed_paths(sys.stdin.readlines())
    wanted = required_sections(every, added)
    if not wanted:
        print("no files in the diff — nothing to require")
        return 0

    template = TEMPLATE.read_text(encoding="utf-8") if TEMPLATE.is_file() else ""
    findings = check(body, every, added, template)

    print(f"required by this diff: {', '.join(sorted(wanted))}")
    for finding in findings:
        print(finding.annotation())

    if findings:
        print(
            "\nAdd the sections, or delete one and say why in the body. If the whole "
            "check genuinely does not apply, put this in the body:\n"
            "  <!-- pr-body-check: skip — <why> -->\n"
            "Prefer that over --admin, which skips every other check too."
        )
        return 1

    print("PR body carries every section this diff calls for")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
