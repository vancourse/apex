"""Every composition root, and the seams each must compose.

Add a root here and tests/test_root_parity.py holds it to the same parity as
the others: every seam in SEAMS, every schedule in schedules.SCHEDULES, every
setting whose consumers include "server" -- unless roots/exclusions.toml names
the omission with a reason and an expiry date.
"""

from __future__ import annotations

ROOTS: dict[str, str] = {
    "app": "__app__.roots.app:build",
}

SEAMS: tuple[str, ...] = ("auth", "clock", "db", "events")
