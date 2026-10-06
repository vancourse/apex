"""R7: identifiers declared once in contracts/registry.py, each with a producer and a consumer.

Fails an emitted event that is undeclared or has no subscriber, a subscriber to
an event nothing emits, a declared schedule with no handler, and any handler
that does nothing -- a lambda, a ``pass``/``...`` body or a constant return.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from typing import Any

from contracts import registry
from scripts.gen import render_registry, stale
from __app__.events import SUBSCRIBERS
from __app__.schedules import SCHEDULES
from tests.astscan import ROOT, parse, python_files, rel


def emitted_events() -> tuple[set[str], list[str]]:
    names: set[str] = set()
    problems: list[str] = []
    for path in python_files():
        for node in ast.walk(parse(path)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "emit"
            ):
                arg = node.args[1] if len(node.args) > 1 else None
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    names.add(arg.value)
                else:
                    problems.append(
                        f"{rel(path)}:{node.lineno}: emit() with a non-literal event name"
                    )
    return names, problems


def noop_reason(fn: Callable[..., Any]) -> str | None:
    """Why `fn` does nothing, or None if it has a real body."""
    fn = inspect.unwrap(getattr(fn, "func", fn))  # functools.partial -> the function
    if getattr(fn, "__name__", "") == "<lambda>":
        return "a lambda"
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    func = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    body = list(func.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
    ):
        body = body[1:]  # docstring
    if all(
        isinstance(s, ast.Pass)
        or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        for s in body
    ):
        return "an empty body (pass / ...)"
    if len(body) == 1 and isinstance(body[0], ast.Return):
        value = body[0].value
        if value is None or isinstance(value, ast.Constant):
            return "a constant return"
    return None


def _handlers() -> list[tuple[str, Callable[..., Any]]]:
    out = [
        (f"event {name} -> {h.__name__}", h)
        for name, hs in SUBSCRIBERS.items()
        for h in hs
    ]
    out += [(f"schedule {name}", s.handler) for name, s in SCHEDULES.items()]
    return out


def test_every_event_is_declared_emitted_and_subscribed() -> None:
    emitted, problems = emitted_events()
    declared, subscribed = (
        set(registry.EVENTS),
        {n for n, hs in SUBSCRIBERS.items() if hs},
    )
    problems += [f"emitted but not declared: {n}" for n in sorted(emitted - declared)]
    problems += [f"declared but never emitted: {n}" for n in sorted(declared - emitted)]
    problems += [
        f"emitted with no subscriber: {n}" for n in sorted(emitted - subscribed)
    ]
    problems += [
        f"subscribed but never emitted: {n}" for n in sorted(subscribed - emitted)
    ]
    assert emitted, (
        "no emit() found under src/ -- the scan is looking in the wrong place"
    )
    assert not problems, "\n".join(problems)


def test_every_schedule_is_declared_and_handled() -> None:
    assert set(registry.SCHEDULES) == set(SCHEDULES), (
        f"registry {sorted(registry.SCHEDULES)} != schedules.py {sorted(SCHEDULES)}"
    )
    assert all(callable(s.handler) for s in SCHEDULES.values())


def test_no_handler_is_a_noop() -> None:
    handlers = _handlers()
    assert handlers, "no handlers found"
    noops = [f"{label}: {why}" for label, h in handlers if (why := noop_reason(h))]
    assert not noops, "handlers that do nothing:\n" + "\n".join(noops)


def _pass(conn: object, payload: object) -> None:
    pass


def _ellipsis(conn: object, payload: object) -> None:
    """Documented, still empty."""
    ...


def _constant(conn: object, payload: object) -> int:
    return 0


def _real(conn: object, payload: object) -> None:
    print(conn, payload)


def test_noop_detector_catches_planted_handlers() -> None:
    assert noop_reason(_pass) == "an empty body (pass / ...)"
    assert noop_reason(_ellipsis) == "an empty body (pass / ...)"
    assert noop_reason(_constant) == "a constant return"
    assert noop_reason(lambda conn, payload: None) == "a lambda"
    assert noop_reason(_real) is None


def test_screen_states_generate_the_frontend_union() -> None:
    drift = stale(render_registry(ROOT))
    assert not drift, (
        f"stale: {[rel(p) for p in drift]} -- run `uv run python scripts/gen.py registry`"
    )
