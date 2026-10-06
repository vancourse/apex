"""Named limits. Every bound in src/ is one of these names.

tests/test_limits_lint.py fails an integer literal in a bounding comparison
(``len(x) > 5``), ``LIMIT 50`` in SQL and ``.limit(50)``. A name here is
greppable, reviewable, and -- for an admission cap -- tested under concurrency.
"""

from __future__ import annotations

ENTRIES_PER_DAY = 5  # entries one member may record per member-local day
PAGE_SIZE = 50  # entries returned per request
NOTE_MAX_CHARS = 200
TOKEN_MAX_CHARS = 128
ACTIVITY_RETENTION_DAYS = 90
PRUNE_ACTIVITY_EVERY_S = 86_400

# Admission caps. tests/test_caps_parallel.py runs cap+3 concurrent admits for
# each name here against the real database and requires exactly cap to succeed.
CAPS: tuple[str, ...] = ("ENTRIES_PER_DAY",)
