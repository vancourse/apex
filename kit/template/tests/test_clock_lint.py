"""R10: the wall clock is read in clock.py and nowhere else; engines take a clock.

Fails ``datetime.now/utcnow/today``, ``date.today`` and ``time.time`` anywhere
under src/ or contracts/ outside clock.py, and any ``clock`` parameter with a
default (a default is how the pinned clock gets forgotten).
"""

from __future__ import annotations

import ast
from datetime import date

import pytest

from __app__.clock import PinnedClock, member_today, parse_instant
from tests.astscan import dotted, parse, python_files, rel

FORBIDDEN = {
    "datetime.now",
    "datetime.utcnow",
    "datetime.today",
    "datetime.datetime.now",
    "datetime.datetime.utcnow",
    "datetime.datetime.today",
    "date.today",
    "datetime.date.today",
    "time.time",
}


def wall_clock_reads(tree: ast.AST) -> list[tuple[int, str]]:
    from_time = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "time"
        for alias in node.names
        if alias.name == "time"
    }
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted(node.func)
        tail = ".".join(name.split(".")[-2:])
        if (
            name in FORBIDDEN
            or tail in FORBIDDEN
            or (isinstance(node.func, ast.Name) and name in from_time)
        ):
            found.append((node.lineno, name))
    return found


def clock_defaults(tree: ast.AST) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            positional = args.posonlyargs + args.args
            defaults = dict(
                zip(
                    [a.arg for a in positional[len(positional) - len(args.defaults) :]],
                    args.defaults,
                    strict=True,
                )
            )
            defaults.update(
                {
                    a.arg: d
                    for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True)
                    if d is not None
                }
            )
            if "clock" in defaults:
                found.append((node.lineno, node.name))
    return found


def test_no_wall_clock_reads_outside_clock_py() -> None:
    problems = [
        f"{rel(path)}:{line}: {name}() -- take a Clock and call clock.now()"
        for path in python_files(skip=("clock.py",))
        for line, name in wall_clock_reads(parse(path))
    ]
    assert not problems, "\n".join(problems)


def test_engines_take_clock_without_a_default() -> None:
    problems = [
        f"{rel(path)}:{line}: {fn}(clock=...) has a default"
        for path in python_files()
        for line, fn in clock_defaults(parse(path))
    ]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    "snippet",
    [
        "from datetime import datetime\nx = datetime.now()",
        "import datetime\nx = datetime.datetime.utcnow()",
        "import datetime as dt\nx = dt.datetime.now()",
        "from datetime import date\nx = date.today()",
        "import time\nx = time.time()",
        "from time import time\nx = time()",
    ],
)
def test_lint_catches_a_planted_wall_clock_read(snippet: str) -> None:
    assert wall_clock_reads(ast.parse(snippet))


def test_lint_catches_a_clock_default() -> None:
    assert clock_defaults(ast.parse("def f(db, clock=None):\n    return clock"))
    assert clock_defaults(
        ast.parse("def f(db, *, clock=WallClock()):\n    return clock")
    )
    assert not clock_defaults(ast.parse("def f(db, *, clock):\n    return clock"))


def test_today_is_the_members_today() -> None:
    clock = PinnedClock(parse_instant("2026-01-31T11:30:00Z"))
    assert member_today(clock, "Pacific/Auckland") == date(2026, 2, 1)
    assert member_today(clock, "UTC") == date(2026, 1, 31)
