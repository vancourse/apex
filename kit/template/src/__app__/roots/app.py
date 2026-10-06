"""The serving root: FastAPI app, seams, schedules -- composed from settings alone.

Building connects to nothing (scripts/gen.py builds it to read the route table);
the database factory checks its role on first use.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from __app__ import routes
from __app__.auth import DevTokenAuth
from __app__.clock import from_as_of
from __app__.db import Database, UnsafeRole
from __app__.events import SUBSCRIBERS, EventBus
from __app__.roots import Composition, ConfigReads, api_routes
from __app__.schedules import SCHEDULES, ScheduleContext
from __app__.settings import Settings


def build(settings: Settings) -> Composition:
    cfg = ConfigReads(settings)
    clock = from_as_of(cfg.as_of)
    db = Database(cfg.database_url.get_secret_value())
    bus = EventBus(SUBSCRIBERS)
    auth = DevTokenAuth(db) if cfg.allow_dev_auth else None

    seams: dict[str, object | None] = {
        "auth": auth,
        "clock": clock,
        "db": db,
        "events": bus,
    }
    ctx = ScheduleContext(db=db, clock=clock)
    schedules = {name: partial(s.handler, ctx) for name, s in SCHEDULES.items()}

    app = FastAPI(title="__App__")
    routes.mount(app)

    @app.exception_handler(psycopg.OperationalError)
    def _database_down(
        _request: Request, _exc: psycopg.OperationalError
    ) -> JSONResponse:
        return JSONResponse({"detail": "database unavailable"}, status_code=503)

    @app.exception_handler(UnsafeRole)
    def _unsafe_role(_request: Request, exc: UnsafeRole) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    static_dir = cfg.static_dir
    if static_dir:
        app.mount(
            "/", StaticFiles(directory=Path(static_dir), html=True), name="static"
        )

    comp = Composition(
        app=app,
        config_fields=frozenset(),
        seams=seams,
        schedules=dict(schedules),
        routes=[(m, r.path) for r in api_routes(app) for m in sorted(r.methods or ())],
        bind=(cfg.host, cfg.port),
    )
    race_window_s = cfg.admit_race_window_ms / 1000
    comp.config_fields = frozenset(cfg.read)
    comp.assert_no_null_seams()
    app.state.wiring = routes.Wiring(
        auth=auth,  # type: ignore[arg-type]  # proven non-None just above
        clock=clock,
        db=db,
        events=bus,
        race_window_s=race_window_s,
    )
    app.state.composition = comp
    return comp
