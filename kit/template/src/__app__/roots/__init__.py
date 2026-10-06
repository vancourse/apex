"""Composition roots: the only places seams are wired.

A root is ``build(settings) -> Composition`` and ends in
``assert_no_null_seams()``, so a seam left ``None`` refuses to boot instead of
failing on the first request that touches it. tests/test_root_parity.py builds
every root in registry.ROOTS and fails one that omits a seam, a schedule or a
server setting that roots/exclusions.toml does not excuse.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.routing import Mount, Route


class NullSeam(RuntimeError):
    """A root composed a seam as None."""


@dataclass
class Composition:
    app: FastAPI
    config_fields: frozenset[str]  # ENV names the root actually read while building
    seams: dict[str, object | None]
    schedules: dict[str, Callable[[], object] | None]
    routes: list[tuple[str, str]] = field(default_factory=list)  # (METHOD, path)
    bind: tuple[str, int] = ("127.0.0.1", 8000)

    def assert_no_null_seams(self) -> None:
        null = sorted(name for name, seam in self.seams.items() if seam is None)
        if null:
            raise NullSeam(
                f"root composed null seam(s): {', '.join(null)}; refusing to boot"
            )
        unhandled = sorted(
            name for name, handler in self.schedules.items() if handler is None
        )
        if unhandled:
            raise NullSeam(f"schedule(s) without a handler: {', '.join(unhandled)}")


class ConfigReads:
    """Wraps Settings and records every field read, so config_fields is observed."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self.read: set[str] = set()

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._settings, name)
        self.read.add(name.upper())
        return value


def api_routes(app: FastAPI) -> list[APIRoute]:
    """Every APIRoute the app serves.

    A route container this cannot see into (an included sub-router, say) raises,
    so an enumeration never comes back silently short -- the auth matrix, the
    contract tests and the client generator all read this.
    """
    found = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            found.append(route)
        elif isinstance(route, (Route, Mount)):
            continue  # starlette's own pages (docs, openapi) and the static mount
        else:
            raise TypeError(
                f"cannot enumerate routes inside {type(route).__name__}; declare them with routes.route()"
            )
    return found
