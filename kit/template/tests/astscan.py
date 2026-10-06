"""The source the AST lints read: everything under src/ and contracts/."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED = (ROOT / "src", ROOT / "contracts")


def python_files(*, skip: tuple[str, ...] = ()) -> Iterator[Path]:
    """Every .py under the scanned roots, minus files whose name is in `skip`."""
    for base in SCANNED:
        for path in sorted(base.rglob("*.py")):
            if path.name not in skip and "__pycache__" not in path.parts:
                yield path


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def dotted(node: ast.AST) -> str:
    """`a.b.c` for a Name/Attribute chain, else ''."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""
