"""GitHub tracker adapter — the universal `gh`-CLI binding (design §A.1).

fetch_issue (READ, P2) + comment (contract verb; MVP-called only downstream). Producer-side
normalization: returns NormalizedIssue, so investigate-bug never parses raw `gh --json`.
The parse core is pure (testable without `gh` installed). Stdlib only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from contracts import AdapterError, AdapterErrorCode, NormalizedIssue  # noqa: E402

# A runner is injected so tests don't need `gh`. Default shells out to gh.
Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]

_FIELDS = "number,title,body,labels,comments,url"


def _default_runner(argv: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(argv, capture_output=True, text=True, timeout=30)


def parse_gh_issue(data: dict) -> NormalizedIssue:
    """Pure: map `gh issue view --json` output to NormalizedIssue. MALFORMED on bad shape."""
    try:
        return NormalizedIssue(
            id=str(data["number"]),
            title=data.get("title", ""),
            body=data.get("body", "") or "",
            labels=[
                lbl["name"] if isinstance(lbl, dict) else str(lbl)
                for lbl in data.get("labels", [])
            ],
            comments=[
                c["body"] if isinstance(c, dict) else str(c)
                for c in data.get("comments", [])
            ],
            url=data.get("url", ""),
        )
    except (KeyError, TypeError) as exc:
        raise AdapterError(
            AdapterErrorCode.MALFORMED, f"unexpected gh issue shape: {exc}"
        ) from exc


def _classify(stderr: str) -> AdapterErrorCode:
    s = stderr.lower()
    if "not found" in s or "could not resolve" in s:
        return AdapterErrorCode.NOT_FOUND
    # 403 is most often forbidden/permission, not rate-limit → AUTH; genuine rate-limits say so.
    if "rate limit" in s or "api rate limit exceeded" in s:
        return AdapterErrorCode.RATE_LIMIT
    if (
        "auth" in s
        or "gh auth login" in s
        or "401" in s
        or "403" in s
        or "forbidden" in s
    ):
        return AdapterErrorCode.AUTH
    return AdapterErrorCode.UNAVAILABLE


class GhTrackerAdapter:
    def __init__(self, runner: Runner | None = None) -> None:
        self._run = runner or _default_runner

    def _exec(self, argv: list[str], what: str):
        """Run gh, mapping EVERY raw subprocess failure to an AdapterError (the §A.1/§E.6
        contract — no raw TimeoutExpired/FileNotFoundError escapes to the caller)."""
        try:
            return self._run(argv)
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                AdapterErrorCode.UNAVAILABLE, f"{what} timed out: {exc}"
            ) from exc
        except (FileNotFoundError, OSError) as exc:
            raise AdapterError(
                AdapterErrorCode.UNAVAILABLE, f"{what}: gh not runnable: {exc}"
            ) from exc

    def fetch_issue(self, ref: str) -> NormalizedIssue:
        out = self._exec(
            ["gh", "issue", "view", ref, "--json", _FIELDS], "gh issue view"
        )
        if out.returncode != 0:
            raise AdapterError(
                _classify(out.stderr), out.stderr.strip() or "gh issue view failed"
            )
        try:
            data = json.loads(out.stdout)
        except json.JSONDecodeError as exc:
            raise AdapterError(
                AdapterErrorCode.MALFORMED, f"gh returned non-JSON: {exc}"
            ) from exc
        return parse_gh_issue(data)

    def comment(self, ref: str, body: str) -> None:
        out = self._exec(
            ["gh", "issue", "comment", ref, "--body", body], "gh issue comment"
        )
        if out.returncode != 0:
            raise AdapterError(
                _classify(out.stderr), out.stderr.strip() or "gh issue comment failed"
            )
