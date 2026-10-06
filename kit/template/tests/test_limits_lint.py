"""R15 limits_gate: every bound in src/ is a name from limits.py.

Fails an integer literal (other than -1, 0, 1) in a bounding comparison,
``LIMIT <digits>`` in a SQL string, and ``.limit(<digits>)``.
"""

from __future__ import annotations

import ast
import re

import pytest

from tests.astscan import parse, python_files, rel

BOUNDING = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
TRIVIAL = {-1, 0, 1}
SQL_LIMIT = re.compile(r"\b(LIMIT|FETCH\s+FIRST)\s+\d+", re.IGNORECASE)


def _int_literal(node: ast.AST) -> int | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _int_literal(node.operand)
        return None if inner is None else -inner
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    return None


def literal_bounds(tree: ast.AST) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(
            isinstance(op, BOUNDING) for op in node.ops
        ):
            for side in [node.left, *node.comparators]:
                value = _int_literal(side)
                if value is not None and value not in TRIVIAL:
                    found.append((node.lineno, f"literal {value} in a comparison"))
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and (match := SQL_LIMIT.search(node.value))
        ):
            found.append((node.lineno, f"SQL {match.group(0)!r}"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "limit"
            and node.args
            and _int_literal(node.args[0]) is not None
        ):
            found.append((node.lineno, f".limit({_int_literal(node.args[0])})"))
    return found


def test_no_literal_bounds_in_src() -> None:
    problems = [
        f"{rel(path)}:{line}: {why} -- name it in limits.py"
        for path in python_files(skip=("limits.py",))
        for line, why in literal_bounds(parse(path))
    ]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    "snippet",
    [
        "if len(rows) > 5:\n    pass",
        "ok = count >= 10",
        "ok = 3 < n",
        'q = "SELECT id FROM entries ORDER BY id LIMIT 50"',
        "rows = query.limit(20)",
    ],
)
def test_lint_catches_a_planted_bound(snippet: str) -> None:
    assert literal_bounds(ast.parse(snippet))


@pytest.mark.parametrize(
    "snippet",
    [
        "if len(rows) > 0:\n    pass",
        "ok = count >= limits.ENTRIES_PER_DAY",
        'q = "SELECT id FROM entries LIMIT %(limit)s"',
        "rows = query.limit(limits.PAGE_SIZE)",
        "x = n == 50",
    ],
)
def test_lint_passes_named_and_trivial_bounds(snippet: str) -> None:
    assert not literal_bounds(ast.parse(snippet))
