"""Deny an agent command that posts a commit status directly (design R25).

A commit status is what CI and the verifier read as "this lane ran and passed
at this SHA". The rails post them from a receipt — ``rails check --post`` /
``rails post`` run the lane, write a receipt the dispatcher observed, and post
``rails/<lane>`` from it. A status the agent posts through ``gh api`` or
``curl`` is a self-certified green: nothing ran that a receipt can point to
(R25: "self-certified artifacts"; decision 7: "an artifact the agent writes
proves nothing by itself").

Refused: ``gh api`` on ``repos/<o>/<r>/statuses/<sha>`` with a body (``-f``,
``-F``, ``--field``, ``--raw-field``, ``--input``) or ``-X``/``--method POST``;
``curl``/``wget``/``Invoke-RestMethod``/``Invoke-WebRequest`` on any
``/statuses/`` URL. A ``gh api`` GET of the same path (no body, no POST) is a
read and passes. The plugin CLI posts through its own process, never through
the agent's command text, so it is unaffected.

Ships in SHADOW until 2026-10-13. The only switch is ``RAILS_STATUS_FORGE_OK``
in the hook's own environment.
"""

from __future__ import annotations

import re

from rails.gates.destructive import command_name, commands
from rails.hookio import Deny, Event
from rails.shell.override import in_environment

NAME = "status_forge"

OVERRIDES = ("RAILS_STATUS_FORGE_OK",)

_STATUSES = re.compile(r"(?:^|/)statuses/[^/\s]+")
_ANY_STATUSES = re.compile(r"/statuses/")
_HTTP_CLIENTS = frozenset(
    {"curl", "wget", "http", "invoke-restmethod", "irm", "invoke-webrequest", "iwr"}
)
_BODY_FLAGS = ("-f", "-F", "--field", "--raw-field", "--input")

MESSAGE = (
    "statuses are posted by `rails check --post` from a receipt; post them that way"
)


def _writes(args: list[str]) -> bool:
    """A body or an explicit POST; an explicit GET turns fields into a query."""
    for index, tok in enumerate(args):
        if tok in ("-X", "--method") and index + 1 < len(args):
            if args[index + 1].upper() == "GET":
                return False
        if tok.upper() in ("-XGET", "--METHOD=GET"):
            return False
    for index, tok in enumerate(args):
        if tok in _BODY_FLAGS or tok.startswith(
            ("--field=", "--raw-field=", "--input=")
        ):
            return True
        if tok[:2] in ("-f", "-F") and len(tok) > 2:
            return True
        if tok in ("-X", "--method") and index + 1 < len(args):
            if args[index + 1].upper() == "POST":
                return True
        if tok.upper() in ("-XPOST", "--METHOD=POST"):
            return True
    return False


def _forges(tokens: list[str]) -> bool:
    name = command_name(tokens[0])
    if name == "gh" and len(tokens) > 1 and tokens[1] == "api":
        args = tokens[2:]
        return any(_STATUSES.search(tok) for tok in args) and _writes(args)
    if name in _HTTP_CLIENTS:
        return any(_ANY_STATUSES.search(tok) for tok in tokens[1:])
    return False


def check(evt: Event) -> Deny | None:
    shell = evt.shell
    if shell is None:
        return None
    command = evt.command
    if not command or in_environment(*OVERRIDES):
        return None
    for segment, tokens in commands(command, shell):
        if _forges(tokens):
            shown = " ".join(segment.split())[:160]
            return Deny(
                f"{MESSAGE}.\n"
                f"    {shown}\n\n"
                f"A status posted from the agent's own command line is a self-certified\n"
                f"green: no receipt shows the lane ran at this SHA, so the verifier and\n"
                f"CI would be trusting the sentence that posted it."
            )
    return None
