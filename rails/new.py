"""rails new <app> -- the starter kit, generated from kit/template, never hand-kept.

    python -m rails.new <name> [--dest DIR] [--rails-ref REF]

Copies ``kit/template`` into an EMPTY destination, substituting tokens in file
contents and in paths:

    __app__          python package / snake_case name     my_app
    __app_kebab__    distribution / npm name             my-app
    __App__          human title                          My App
    __RAILS_REF__    the plugin ref CI actions pin to     main
    __EXPIRES__      default expiry for dated exclusions  today + 180 days
    __TODAY__        generation date                      today

and writes ``.rails-kit.json`` ({"kit_version", "rails_ref"}). When the plugin
ships document templates (``templates/`` or ``rails/templates/``), its
``spec.md`` and ``milestone.md`` replace the kit's minimal ones.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

KIT_VERSION = "1"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = PLUGIN_ROOT / "kit" / "template"
DOC_TEMPLATES = (PLUGIN_ROOT / "templates", PLUGIN_ROOT / "rails" / "templates")
SEEDED_DOCS = ("spec.md", "milestone.md")
# Never copied: dependency trees, caches and build output a template dir can pick
# up when someone runs a tool inside it.
SKIP = frozenset(
    {
        "node_modules",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "dist",
        ".rails-kit.json",
    }
)
NAME = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$")
# Top-level packages the generated app already has, and the dependencies it
# imports -- a same-named app package would shadow either.
RESERVED = frozenset(
    {
        "contracts",
        "oracle",
        "tests",
        "scripts",
        "fixtures",
        "deploy",
        "migrations",
        "frontend",
        "wire",
    }
    | {
        "fastapi",
        "pydantic",
        "psycopg",
        "uvicorn",
        "starlette",
        "httpx",
        "pytest",
        "tzdata",
        "hatchling",
    }
)
TOKEN = re.compile(r"__(?:app|app_kebab|App|RAILS_REF|EXPIRES|TODAY)__")


class KitError(ValueError):
    """The name, destination or template is unusable."""


def tokens(name: str, rails_ref: str, today: date) -> dict[str, str]:
    snake = name.replace("-", "_")
    return {
        # longest first: no token is a substring of another, but keep it obvious
        "__app_kebab__": name.replace("_", "-"),
        "__RAILS_REF__": rails_ref,
        "__EXPIRES__": (today + timedelta(days=180)).isoformat(),
        "__TODAY__": today.isoformat(),
        "__app__": snake,
        "__App__": " ".join(part.capitalize() for part in re.split(r"[-_]", name)),
    }


def substitute(text: str, table: dict[str, str]) -> str:
    for token, value in table.items():
        text = text.replace(token, value)
    return text


def check_name(name: str) -> None:
    if not NAME.match(name):
        raise KitError(
            f"app name {name!r}: use lower-case letters, digits, '-' or '_', starting with a letter"
        )
    snake = name.replace("-", "_")
    if snake in RESERVED or snake in sys.stdlib_module_names:
        raise KitError(
            f"app name {name!r} collides with {'a kit package or dependency' if snake in RESERVED else 'a stdlib module'}"
        )


def _doc_override(name: str) -> Path | None:
    for directory in DOC_TEMPLATES:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _files(template: Path) -> list[Path]:
    return sorted(
        p
        for p in template.rglob("*")
        if p.is_file() and not SKIP.intersection(p.relative_to(template).parts)
    )


def new(
    name: str, dest: Path, *, rails_ref: str = "main", template: Path = TEMPLATE
) -> Path:
    """Generate the kit for app `name` into `dest` (created; must be empty). Returns `dest`."""
    check_name(name)
    dest = Path(dest)
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise KitError(
            f"refusing to write into {dest}: it exists and is not an empty directory"
        )
    if not template.is_dir():
        raise KitError(f"kit template not found at {template}")
    table = tokens(name, rails_ref, date.today())
    dest.mkdir(parents=True, exist_ok=True)

    for source in _files(template):
        relative = source.relative_to(template)
        fill = table
        if relative.parts[0] == "docs" and relative.name in SEEDED_DOCS:
            override = _doc_override(relative.name)
            if override is not None:
                source = override
                # the plugin's document templates are generic; name the app in them
                fill = {
                    **table,
                    "<Component>": table["__App__"],
                    "<App>": table["__App__"],
                    "R<n>": "R1",
                }
        target = dest / substitute(relative.as_posix(), table)
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            target.write_bytes(raw)  # binary: copied as-is
            continue
        out = substitute(text.replace("\r\n", "\n"), fill)
        leftover = TOKEN.search(out)
        if leftover:
            raise KitError(f"{relative}: unsubstituted token {leftover.group(0)}")
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(out)

    manifest = {"kit_version": KIT_VERSION, "rails_ref": rails_ref}
    with open(dest / ".rails-kit.json", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2) + "\n")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rails new", description="generate the rails starter kit"
    )
    parser.add_argument("name", help="app name: lower-case, '-' or '_' between words")
    parser.add_argument(
        "--dest", type=Path, help="target directory (default: ./<name>); must be empty"
    )
    parser.add_argument(
        "--rails-ref",
        default="main",
        help="plugin ref the generated CI pins (default: main)",
    )
    args = parser.parse_args(argv)
    try:
        dest = new(
            args.name, args.dest or Path.cwd() / args.name, rails_ref=args.rails_ref
        )
    except KitError as exc:
        print(f"rails new: {exc}", file=sys.stderr)
        return 2
    print(f"rails new: wrote {dest}")
    print(
        "next: uv sync && uv run pytest -q; pnpm --dir frontend install && pnpm --dir frontend run check"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
