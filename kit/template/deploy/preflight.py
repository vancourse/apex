"""Refuse to bring a deployment up with a required setting missing.

    python deploy/preflight.py [--env-file deploy/.env.prod]

Reads the names from deploy/preflight_names.txt (generated from settings.toml)
and prints each name with present/MISSING -- never a value. Exit 1 when any
required name is missing or empty. Stdlib only: it runs before anything is
installed.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path

NAMES = Path(__file__).resolve().with_name("preflight_names.txt")


def _names(path: Path = NAMES) -> list[tuple[str, bool]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, flag = line.split()
        out.append((name, flag == "required"))
    return out


def _env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def check(environ: Mapping[str, str]) -> int:
    missing = 0
    for name, required in _names():
        present = bool(environ.get(name, ""))
        state = (
            "present" if present else ("MISSING" if required else "unset (optional)")
        )
        print(f"{name}: {state}")
        missing += required and not present
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deploy/preflight.py")
    parser.add_argument(
        "--env-file", type=Path, help="check this file instead of the environment"
    )
    args = parser.parse_args(argv)
    return check(_env_file(args.env_file) if args.env_file else os.environ)


if __name__ == "__main__":
    sys.exit(main())
