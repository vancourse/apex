"""The walk lane: the real root serving the built frontend over a planted database,
and frontend/e2e/walk.mjs clicking through it.

    uv run python scripts/walk.py [--no-build]

A throwaway ``rails_planted_*`` database is created, migrated and seeded, then
dropped. AS_OF comes from the planted corpus and reaches the server through the
same settings row production reads. The server runs in this process (a thread),
so nothing is left listening when the walk ends. Exit code is the walk's; its
last stdout line is the receipt JSON.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import uvicorn  # noqa: E402

from oracle.checker import load_corpus  # noqa: E402
from __app__.roots.app import build  # noqa: E402
from __app__.settings import load_settings  # noqa: E402
from tests.planted_db import planted_database  # noqa: E402

FRONTEND = ROOT / "frontend"


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"walk: {name} not found on PATH")
    return path


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts/walk.py")
    parser.add_argument("--no-build", action="store_true", help="reuse frontend/dist")
    args = parser.parse_args(argv)
    if not args.no_build:
        subprocess.run([_tool("pnpm"), "run", "build"], cwd=FRONTEND, check=True)
    corpus = load_corpus()
    token = next(
        m["token"] for m in corpus["member"] if m["id"] == corpus["walk_member"]
    )
    port = _free_port()
    with planted_database(corpus=corpus) as planted:
        settings = load_settings(
            {
                "DATABASE_URL": planted.app_dsn,
                "AS_OF": corpus["as_of"],
                "ALLOW_DEV_AUTH": "true",
                "STATIC_DIR": str(FRONTEND / "dist"),
                "HOST": "127.0.0.1",
                "PORT": str(port),
            }
        )
        comp = build(settings)
        host, bound = comp.bind
        server = uvicorn.Server(
            uvicorn.Config(comp.app, host=host, port=bound, log_level="warning")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            while not server.started:
                if not thread.is_alive():
                    raise SystemExit("walk: the server exited before it started")
                thread.join(timeout=0.05)
            env = {
                **os.environ,
                "BASE_URL": f"http://{host}:{bound}",
                "MEMBER_TOKEN": token,
            }
            return subprocess.run(
                [_tool("node"), "e2e/walk.mjs"], cwd=FRONTEND, env=env
            ).returncode
        finally:
            server.should_exit = True
            thread.join(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
