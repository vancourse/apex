"""Registry anchor for the pre-push refusals, which run in the git hook, not the dispatcher.

Rows ``prepush_hold``, ``prepush_marker`` and ``prepush_leak`` in hooks/gates.toml
point here so the registry stays the one list of every refusal. The logic is
``rails.githooks.pre_push``; its planted defects are in tests/test_githooks.py.
The dispatcher never matches these rows: their only event is ``git:pre-push``.
"""

from __future__ import annotations

NAME = "prepush"


def check(evt):  # pragma: no cover - never dispatched
    return None
