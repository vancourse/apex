"""DEV-ONLY member resolution. This is NOT an authentication scheme.

``X-Member: <token>`` names a planted member. It exists so the skeleton, its
tests and the walk can act as a member of a household before the app has real
sign-in. The root composes it only when ALLOW_DEV_AUTH is true and otherwise
refuses to boot (a None ``auth`` seam), so a deployment cannot drift into it.
Replace this seam with real sign-in; keep its interface: ``resolve(token)``.
"""

from __future__ import annotations

import re

from __app__ import limits
from __app__.db import Database
from __app__.ledger import Member, resolve_token

_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


class DevTokenAuth:
    def __init__(self, db: Database) -> None:
        self._db = db

    def resolve(self, token: str | None) -> Member | None:
        if not token or len(token) > limits.TOKEN_MAX_CHARS or not _TOKEN.match(token):
            return None
        return resolve_token(self._db, token)
