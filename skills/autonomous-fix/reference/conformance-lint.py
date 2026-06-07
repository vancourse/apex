#!/usr/bin/env python3
"""conformance-lint.py — apex autonomous-fix template-shape conformance lint.

Statically checks the SIX template-shape ACs (AC2/AC4/AC5/AC6/AC7a/AC9) over ONE
GitHub-Actions reference template. It does NOT touch the runtime ACs
(AC1/AC3/AC7b/AC8) — those are the adopting project's wired runtime + GH
branch-protection (design.md "Deferral #9, rejected not deferred").

Seven checks (the design.md lint table), each decidable on the single file:

  check_title_in_fence        AC2       single-step/single-block prompt; every
                                        github.event.* interpolation sits between
                                        the nonce markers (the title-injection fix)
  check_nonce_delimiter       AC2/N2    close marker == open marker AND the marker
                                        carries a ${...} interpolation (S3.4)
  check_gate_names            AC4       each composed gate name is a prompt substring
  check_cost_cap_present     AC5/B3    a budget-precheck step exists; turn + timeout
                                        + concurrency present; fail-CLOSED (no
                                        continue-on-error, no `:-0`/default-to-zero)
  check_no_merge             AC6       no merge / --auto / force-push / push-to-
                                        protected; a --draft open exists
                                        (author-hygiene only; branch-protection is
                                        the real AC6 enforcer)
  check_default_deny_allowlist AC7a    two distinct concrete allowed_tools arrays
                                        (read-only(+test-write) and write), neither
                                        '*' / an open shell
  check_mode_parity          AC9       exactly one mode-conditional step (the
                                        confirm step); no budget/allowlist/fence/
                                        sensitive key under any mode conditional

Usage:  python conformance-lint.py <path-to-template.yml>
Exit:   0 iff all seven checks PASS; non-zero otherwise.

Dependencies: Python 3 stdlib + PyYAML only.
"""

from __future__ import annotations

import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write("conformance-lint: PyYAML is required (pip install pyyaml).\n")
    sys.exit(2)


# ── Constants ──────────────────────────────────────────────────────────────

# The composed apex gates the operating prompt must name (AC4 / design.md:271).
GATE_NAMES = [
    "systematic-debugging",
    "security-review",
    "threat-model",
    "ai-pre-review-checklist",
    "pr-discipline",
]

# Any GitHub-context interpolation that carries attacker-controllable input.
# The TITLE is the load-bearing one (the BookBridge :165-vs-:174 hole, AC2/N2).
UNTRUSTED_INTERP = re.compile(
    r"\$\{\{\s*github\.event\.issue\.[a-zA-Z0-9_.*()'\", ]+\}\}"
)

# Marker pair: <UNTRUSTED_FIELD_${...}> ... </UNTRUSTED_FIELD_${...}>.
OPEN_MARKER = re.compile(r"<(UNTRUSTED_[A-Z]+_\$\{[^>]*\})>")
CLOSE_MARKER = re.compile(r"</(UNTRUSTED_[A-Z]+_\$\{[^>]*\})>")

# Fail-OPEN patterns the budget step must NOT carry (design.md:272 / B3).
CONTINUE_ON_ERROR = re.compile(r"continue-on-error\s*:\s*true", re.IGNORECASE)
DEFAULT_TO_ZERO = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-0\}")  # ${var:-0}

# Merge / auto-merge / force-push / push-to-protected — none may appear (AC6).
MERGE_PATTERNS = [
    re.compile(r"gh\s+pr\s+merge"),
    re.compile(r"--auto\b"),
    re.compile(r"pulls/[^/\s]+/merge"),
    re.compile(r"/merge\b.*--method", re.IGNORECASE),
    re.compile(r"push\s+.*--force\b"),
    re.compile(r"push\s+.*-f\b"),
    re.compile(r"--force-with-lease\b"),
    re.compile(r"auto[_-]?merge\s*:\s*true", re.IGNORECASE),
]
DRAFT_OPEN = re.compile(r"gh\s+pr\s+create\b.*--draft", re.DOTALL)

# An open-shell / wildcard allowlist (AC7a forbids it).
OPEN_ALLOWLIST_TOKENS = {"*", "Bash", "Bash(*)", "Bash(*:*)", "all", "any"}

# The single legal mode conditional (AC9 — the confirm step only).
MODE_CONDITIONAL = re.compile(
    r"\b(inputs|env|github\.event\.inputs)\.(mode|run_?mode)\b", re.IGNORECASE
)

# Keys that must NEVER sit under a mode conditional (AC9 parity / B6).
PARITY_FORBIDDEN_KEYS = (
    "budget",
    "allowed_tools",
    "allowlist",
    "sensitive",
    "fence",
    "nonce",
    "cost",
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    # YAML 1.1: a bare `on:` key parses to the boolean True — harmless here since
    # every structural check that needs `on:` works off the raw text. PyYAML still
    # parses the rest of the document into the tree we walk for steps/keys.
    tree = yaml.safe_load(raw)
    return raw, tree


def _iter_steps(tree):
    """Yield (job_name, step_dict) for every step in every job."""
    jobs = (tree or {}).get("jobs") or {}
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict):
                yield job_name, step


def _step_text(step):
    """Flatten a step's run/with/name/env into one searchable string."""
    parts = [str(step.get("name", "")), str(step.get("run", ""))]
    with_block = step.get("with")
    if isinstance(with_block, dict):
        for k, v in with_block.items():
            parts.append(f"{k}: {v}")
    env_block = step.get("env")
    if isinstance(env_block, dict):
        for k, v in env_block.items():
            parts.append(f"{k}: {v}")
    return "\n".join(parts)


def _strip_yaml_comments(raw):
    """Remove `#` comments line-by-line, honoring single/double quotes, so a
    construct mentioned in a COMMENT is not mistaken for an executing one. A `#`
    inside a quoted span (or `${{ ... }}`) is preserved; everything from a real
    comment-start `#` to end-of-line is dropped."""
    out_lines = []
    for line in raw.splitlines():
        in_single = in_double = False
        cut = None
        for i, ch in enumerate(line):
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "#" and not in_single and not in_double:
                # A comment-start: line-start or whitespace-preceded.
                if i == 0 or line[i - 1].isspace():
                    cut = i
                    break
        out_lines.append(line if cut is None else line[:cut])
    return "\n".join(out_lines)


def _find_prompt_run(tree):
    """Return [(step, run)] for the single fenced-prompt step (the build-fenced-prompt step)."""
    candidates = []
    for _job, step in _iter_steps(tree):
        run = step.get("run")
        if isinstance(run, str) and OPEN_MARKER.search(run):
            candidates.append((step, run))
    return candidates


# ── The seven checks. Each returns (passed: bool, detail: str). ─────────────


def check_title_in_fence(raw, tree):
    """AC2 — single-step/single-block prompt; every github.event.* interpolation
    appears between the nonce markers (title included). Reject multi-step or
    env-indirected prompt assembly (B4)."""
    candidates = _find_prompt_run(tree)
    if not candidates:
        return (
            False,
            "no single-block prompt step found (a step whose `run` carries the UNTRUSTED markers)",
        )
    if len(candidates) > 1:
        return (
            False,
            f"prompt is split across {len(candidates)} steps — must be ONE single-block step (B4)",
        )
    _step, run = candidates[0]

    # Reject env-indirected assembly: the untrusted interpolations must be inside
    # THIS run block, not pre-assembled into an env var elsewhere.
    interps = UNTRUSTED_INTERP.findall(run)
    if not interps:
        return (
            False,
            "the prompt step has markers but no github.event.issue.* interpolation inside it",
        )

    # Every untrusted interpolation must sit BETWEEN an open and a close marker.
    open_spans = [m.span() for m in OPEN_MARKER.finditer(run)]
    close_spans = [m.span() for m in CLOSE_MARKER.finditer(run)]
    if not open_spans or not close_spans:
        return False, "prompt is missing an open or close UNTRUSTED marker"
    fenced_regions = []
    for o_start, o_end in open_spans:
        nexts = [c_start for c_start, _ in close_spans if c_start >= o_end]
        if nexts:
            fenced_regions.append((o_end, min(nexts)))

    def inside_fence(pos):
        return any(lo <= pos < hi for lo, hi in fenced_regions)

    title_seen = False
    for m in UNTRUSTED_INTERP.finditer(run):
        if not inside_fence(m.start()):
            return (
                False,
                f"untrusted interpolation OUTSIDE the fence: {m.group(0)!r} (the title-injection hole)",
            )
        if "title" in m.group(0):
            title_seen = True
    if not title_seen:
        return (
            False,
            "the issue TITLE is not interpolated inside the fence (AC2/N2 title-coverage delta)",
        )
    return (
        True,
        f"single-block prompt; {len(interps)} untrusted interpolation(s) all fenced (title included)",
    )


def check_nonce_delimiter(raw, tree):
    """AC2/N2/S3.4 — close marker == open marker AND the marker carries a ${...}
    interpolation (a per-run nonce). Property check, not full provenance (B4)."""
    opens = OPEN_MARKER.findall(raw)
    closes = CLOSE_MARKER.findall(raw)
    if not opens:
        return False, "no UNTRUSTED open marker found"
    if not closes:
        return False, "no UNTRUSTED close marker found"
    if set(opens) != set(closes):
        only_open = set(opens) - set(closes)
        only_close = set(closes) - set(opens)
        return False, (
            "open/close markers differ (marker-injection risk): "
            f"open-only={sorted(only_open)} close-only={sorted(only_close)}"
        )
    bare = [m for m in opens if "${" not in m]
    if bare:
        return (
            False,
            f"marker(s) carry NO ${{...}} nonce interpolation (a literal close-marker is forgeable): {bare}",
        )
    return (
        True,
        f"{len(set(opens))} marker class(es); open==close, each carries a ${{...}} nonce",
    )


def check_gate_names(raw, tree):
    """AC4 — each composed gate name is a substring of the operating prompt."""
    candidates = _find_prompt_run(tree)
    haystack = candidates[0][1] if candidates else raw
    missing = [g for g in GATE_NAMES if g not in haystack]
    if missing:
        return False, f"operating prompt is missing gate name(s): {missing}"
    return True, f"all {len(GATE_NAMES)} gate names present in the prompt"


def check_cost_cap_present(raw, tree):
    """AC5/B3 — a budget-precheck step exists; turn + timeout + concurrency present;
    AND the budget step is fail-CLOSED (no continue-on-error, no `:-0`)."""
    budget_step = None
    for _job, step in _iter_steps(tree):
        name = str(step.get("name", "")).lower()
        if "budget" in name or "cost" in name:
            budget_step = step
            break
    if budget_step is None:
        return False, "no budget-precheck / cost-cap step found"

    # turn budget — a max_turns / MAX_TURNS surface anywhere in the template.
    if not re.search(r"max[_-]?turns", raw, re.IGNORECASE):
        return False, "no turn budget (max_turns) present"

    # wall-clock timeout on the job.
    if "timeout-minutes" not in raw:
        return False, "no wall-clock timeout (timeout-minutes) present"

    # concurrency block keyed per-issue (the single-flight property, S5.3).
    concurrency = (tree or {}).get("concurrency")
    if not concurrency:
        return False, "no top-level concurrency block present"
    if isinstance(concurrency, dict):
        if str(concurrency.get("cancel-in-progress")).lower() == "true":
            return (
                False,
                "concurrency cancel-in-progress is true — a half-applied fix could be cancelled (must be false)",
            )
        if not concurrency.get("group"):
            return False, "concurrency block has no group key"

    # fail-CLOSED: the budget step must NOT carry continue-on-error or `${var:-0}`.
    if str(budget_step.get("continue-on-error")).lower() == "true":
        return (
            False,
            "budget step carries continue-on-error: true — FAIL-OPEN (the BookBridge :69 hole)",
        )
    step_text = _step_text(budget_step)
    if CONTINUE_ON_ERROR.search(step_text):
        return False, "budget step carries continue-on-error: true — FAIL-OPEN"
    if DEFAULT_TO_ZERO.search(step_text):
        return (
            False,
            "budget step uses a `${var:-0}` default-to-zero — FAIL-OPEN (the BookBridge :88 hole)",
        )
    return (
        True,
        "budget-precheck present; turn+timeout+concurrency present; fail-closed (no continue-on-error/`:-0`)",
    )


def check_no_merge(raw, tree):
    """AC6 — no merge / --auto / force-push / push-to-protected; a --draft open
    exists. Scans the COMMENT-STRIPPED template (a construct named in a comment is
    not an executing one). Author-hygiene only; branch-protection is the real
    enforcer (B1)."""
    code = _strip_yaml_comments(raw)
    for pat in MERGE_PATTERNS:
        m = pat.search(code)
        if m:
            return (
                False,
                f"forbidden auto-merge/force-push construct present: {m.group(0)!r}",
            )
    if not DRAFT_OPEN.search(code):
        return (
            False,
            "no `gh pr create --draft` step found (the terminal action must be a DRAFT)",
        )
    return (
        True,
        "no merge/--auto/force-push; a --draft PR open exists (author-hygiene; branch-protection enforces AC6)",
    )


def check_default_deny_allowlist(raw, tree):
    """AC7a — two distinct concrete allowed_tools arrays (read-only(+test-write)
    and write), neither '*' / an open shell (B5)."""
    arrays = []
    for _job, step in _iter_steps(tree):
        with_block = step.get("with")
        if isinstance(with_block, dict) and "allowed_tools" in with_block:
            arrays.append((str(step.get("name", "")), with_block["allowed_tools"]))
    if len(arrays) < 2:
        return (
            False,
            f"need TWO concrete allowed_tools arrays (read-only + write); found {len(arrays)}",
        )

    parsed = []
    for name, value in arrays:
        # Each array is a JSON-ish string; parse leniently into a token set.
        try:
            tokens = yaml.safe_load(value) if isinstance(value, str) else value
        except yaml.YAMLError:
            tokens = None
        if not isinstance(tokens, list):
            # Fall back to splitting on quotes.
            tokens = re.findall(r'"([^"]+)"', str(value))
        token_set = {str(t).strip() for t in tokens if str(t).strip()}
        if not token_set:
            return (
                False,
                f"allowed_tools array on step {name!r} is empty or unparseable",
            )
        open_hits = token_set & OPEN_ALLOWLIST_TOKENS
        if open_hits:
            return (
                False,
                f"allowed_tools on step {name!r} contains an open/wildcard token: {sorted(open_hits)}",
            )
        # An unscoped `Bash` (no parenthesised command filter) is an open shell.
        for tok in token_set:
            if re.fullmatch(r"Bash", tok):
                return (
                    False,
                    f"allowed_tools on step {name!r} has an unscoped Bash (open shell) — must be Bash(cmd:*)",
                )
        parsed.append((name, frozenset(token_set)))

    distinct = {fs for _n, fs in parsed}
    if len(distinct) < 2:
        return (
            False,
            "the two allowed_tools arrays are identical — read-only and write must be DISTINCT (staged unlock)",
        )
    return (
        True,
        f"{len(arrays)} distinct concrete allowed_tools arrays; no '*'/open-shell token",
    )


def check_mode_parity(raw, tree):
    """AC9 — exactly one step is mode-conditional (the confirm step); no
    budget/allowlist/fence/sensitive key sits under any mode conditional (B6)."""
    mode_steps = []
    for _job, step in _iter_steps(tree):
        cond = step.get("if")
        if isinstance(cond, str) and MODE_CONDITIONAL.search(cond):
            mode_steps.append(step)
    if len(mode_steps) == 0:
        return (
            False,
            "no mode-conditional step found (the confirm step must be `if: <mode>`)",
        )
    if len(mode_steps) > 1:
        names = [str(s.get("name", "?")) for s in mode_steps]
        return (
            False,
            f"{len(mode_steps)} mode-conditional steps — exactly ONE (confirm) is legal: {names}",
        )

    # Job-level if must not be mode-gated (would relax the whole rail set per mode).
    for _name, job in ((tree or {}).get("jobs") or {}).items():
        if isinstance(job, dict):
            jcond = job.get("if")
            if isinstance(jcond, str) and MODE_CONDITIONAL.search(jcond):
                return (
                    False,
                    "a JOB-level `if` is mode-conditional — the entire rail set must not toggle on mode",
                )

    # The single mode-conditional step must not carry a rail-bearing key.
    only = mode_steps[0]
    blob = _step_text(only).lower()
    for forbidden in PARITY_FORBIDDEN_KEYS:
        if forbidden in blob:
            return False, (
                f"the mode-conditional step touches a rail-bearing key {forbidden!r} — "
                "only the human-confirm step may be mode-gated (B6)"
            )
    return (
        True,
        "exactly one mode-conditional step (confirm); no budget/allowlist/fence/sensitive key gated on mode",
    )


CHECKS = [
    ("check_title_in_fence", check_title_in_fence),
    ("check_nonce_delimiter", check_nonce_delimiter),
    ("check_gate_names", check_gate_names),
    ("check_cost_cap_present", check_cost_cap_present),
    ("check_no_merge", check_no_merge),
    ("check_default_deny_allowlist", check_default_deny_allowlist),
    ("check_mode_parity", check_mode_parity),
]


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: conformance-lint.py <path-to-template.yml>\n")
        return 2
    path = argv[1]
    try:
        raw, tree = _load(path)
    except FileNotFoundError:
        sys.stderr.write(f"conformance-lint: file not found: {path}\n")
        return 2
    except yaml.YAMLError as exc:
        sys.stderr.write(f"conformance-lint: YAML parse error: {exc}\n")
        return 2

    failures = 0
    for name, fn in CHECKS:
        try:
            passed, detail = fn(raw, tree)
        except (
            Exception
        ) as exc:  # a crashing check is a FAIL, never a silent pass (fail-closed)
            passed, detail = False, f"check crashed: {exc!r}"
        status = "PASS" if passed else "FAIL"
        if not passed:
            failures += 1
        print(f"[{status}] {name}: {detail}")

    print("-" * 60)
    if failures:
        print(f"FAIL — {failures} of {len(CHECKS)} checks failed")
        return 1
    print(f"PASS — all {len(CHECKS)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
