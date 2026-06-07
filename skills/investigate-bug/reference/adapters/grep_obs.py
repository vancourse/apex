"""Console-logs observability adapter — the universal `grep` binding (design §A.2).

query_logs(window, query) over a repo-confined log file. The `query` is matched as an
ESCAPED LITERAL (a plain substring, never a passthrough regex — closes the ReDoS
amplifier, F2). The window is a required positional (the DoS bound). Producer-side:
returns list[LogLine] (parsed ts), so investigate-bug never parses raw grep output.
Stdlib only.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from contracts import AdapterError, AdapterErrorCode, LogLine, TimeWindow  # noqa: E402

# Leading ISO-8601-ish timestamp: 2026-06-07T12:34:56 or 2026-06-07 12:34:56(.ms)(Z)
_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})")


def parse_log_line(line: str, source: str) -> LogLine | None:
    """Pure: parse a leading timestamp → LogLine; None if the line has no parseable ts."""
    m = _TS_RE.match(line)
    if not m:
        return None
    try:
        ts = datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
    except ValueError:
        return None
    return LogLine(ts=ts, text=line.rstrip("\n"), source=source)


def _confined(log_path: Path, repo_root: Path) -> Path:
    """Defense-in-depth (F1): the adapter re-confines its read under the repo root, even if a
    profile bypassed the loader's value-shape check."""
    root = Path(os.path.realpath(repo_root))
    resolved = Path(
        os.path.realpath(log_path if log_path.is_absolute() else root / log_path)
    )
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise AdapterError(
            AdapterErrorCode.MALFORMED, f"log_path escapes the repo root: {resolved}"
        ) from exc
    return resolved


def query_logs(
    window: TimeWindow,
    query: str | None = None,
    log_path: str = "logs/app.log",
    repo_root: Path | None = None,
) -> list[LogLine]:
    """Return the LogLines in [window] whose text contains the literal `query` (if given)."""
    repo_root = repo_root or Path.cwd()
    path = _confined(Path(log_path), repo_root)
    if not path.exists():
        raise AdapterError(
            AdapterErrorCode.NOT_FOUND, f"log file not found: {log_path}"
        )
    source = str(path.relative_to(Path(os.path.realpath(repo_root))))
    # console log timestamps are naive; compare against a naive view of the window so a
    # tz-aware window doesn't raise TypeError mid-read (it maps to a gate terminal, not a crash).
    w_start = window.start.replace(tzinfo=None)
    w_end = window.end.replace(tzinfo=None)
    out: list[LogLine] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                ll = parse_log_line(line, source)
                if ll is None or not (w_start <= ll.ts <= w_end):
                    continue
                if (
                    query is not None and query not in ll.text
                ):  # LITERAL substring, never regex
                    continue
                out.append(ll)
    except OSError as exc:
        raise AdapterError(
            AdapterErrorCode.UNAVAILABLE, f"cannot read {log_path}: {exc}"
        ) from exc
    return out


class GrepObsAdapter:
    """Object form of the obs axis (binds log_path/repo_root) so it satisfies the
    ObservabilityAdapter Protocol uniformly with the tracker adapter (S9 conformance)."""

    def __init__(
        self, log_path: str = "logs/app.log", repo_root: Path | None = None
    ) -> None:
        self._log_path = log_path
        self._repo_root = repo_root

    def query_logs(self, window: TimeWindow, query: str | None = None) -> list[LogLine]:
        return query_logs(
            window, query, log_path=self._log_path, repo_root=self._repo_root
        )
