"""R6: every setting declared once in settings.toml; every consumer generated from it.

Fails when a generated consumer is stale, when src/ reads an environment name
settings.toml does not declare, and when a secret leaks into repr or a log view.
"""

from __future__ import annotations

import ast
import importlib.util

import pytest

from scripts.gen import render_settings, setting_rows, stale
from __app__.settings import SettingsError, load_settings, public_view
from tests.astscan import ROOT, dotted, parse, python_files, rel

GENERATED_READER = "settings.py"  # the one sanctioned os.environ reader (generated)


def env_reads(tree: ast.AST) -> tuple[set[str], list[int]]:
    """(literal names read, lines of reads whose name is not a literal)."""
    names: set[str] = set()
    dynamic: list[int] = []
    environ_aliases = {"os.environ", "environ"}
    getenv_aliases = {"os.getenv", "getenv"}

    def literal(arg: ast.AST, line: int) -> None:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            names.add(arg.value)
        else:
            dynamic.append(line)

    claimed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = dotted(node.func)
            if target in getenv_aliases or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in ("get", "pop", "setdefault")
                and dotted(node.func.value) in environ_aliases
            ):
                literal(node.args[0] if node.args else ast.Constant(None), node.lineno)
                if isinstance(node.func, ast.Attribute):
                    claimed.add(id(node.func.value))
        elif isinstance(node, ast.Subscript) and dotted(node.value) in environ_aliases:
            literal(node.slice, node.lineno)
            claimed.add(id(node.value))
    for node in ast.walk(tree):
        if (
            dotted(node) == "os.environ"
            and id(node) not in claimed
            and isinstance(node, ast.Attribute)
        ):
            dynamic.append(node.lineno)  # the whole mapping handed somewhere
    return names, sorted(dynamic)


def test_generated_settings_are_current() -> None:
    drift = stale(render_settings(ROOT))
    assert not drift, (
        f"stale: {[rel(p) for p in drift]} -- run `uv run python scripts/gen.py settings`"
    )


def test_every_env_read_is_declared() -> None:
    declared = {row["name"] for row in setting_rows(ROOT)}
    problems = []
    for path in python_files(skip=(GENERATED_READER,)):
        names, dynamic = env_reads(parse(path))
        problems += [
            f"{rel(path)}: reads undeclared {name!r}"
            for name in sorted(names - declared)
        ]
        problems += [
            f"{rel(path)}:{line}: environment read with a non-literal name"
            for line in dynamic
        ]
    assert not problems, (
        "declare it in settings.toml and read it through Settings:\n"
        + "\n".join(problems)
    )


@pytest.mark.parametrize(
    "snippet",
    [
        'import os\nX = os.environ.get("UNDECLARED")',
        'import os\nX = os.environ["UNDECLARED"]',
        'import os\nX = os.getenv("UNDECLARED", "")',
        'from os import environ\nX = environ.get("UNDECLARED")',
    ],
)
def test_scanner_finds_a_planted_read(snippet: str) -> None:
    names, _ = env_reads(ast.parse(snippet))
    assert names == {"UNDECLARED"}


def test_scanner_flags_a_dynamic_read() -> None:
    _, dynamic = env_reads(
        ast.parse("import os\nname = 'X'\nY = os.environ[name]\nZ = dict(os.environ)")
    )
    assert dynamic == [3, 4]


def test_secrets_stay_out_of_repr_and_public_view() -> None:
    secret = "postgresql://u:hunter2-planted@127.0.0.1/db"
    settings = load_settings({"DATABASE_URL": secret})
    assert "hunter2-planted" not in repr(settings)
    assert "DATABASE_URL" not in public_view(settings)
    assert settings.database_url.get_secret_value() == secret


def test_a_missing_setting_is_named_never_valued() -> None:
    with pytest.raises(SettingsError, match="DATABASE_URL"):
        load_settings({})
    with pytest.raises(SettingsError, match="PORT: expected an integer") as caught:
        load_settings({"DATABASE_URL": "postgresql://x@h/d", "PORT": "eighty-planted"})
    assert "eighty-planted" not in str(caught.value)


def test_preflight_prints_names_and_presence_never_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec = importlib.util.spec_from_file_location(
        "preflight", ROOT / "deploy" / "preflight.py"
    )
    assert spec is not None and spec.loader is not None
    preflight = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preflight)
    assert preflight.check({"DATABASE_URL": "postgresql://planted-secret@h/d"}) == 0
    assert preflight.check({}) == 1
    out = capsys.readouterr().out
    assert "DATABASE_URL" in out and "planted-secret" not in out


def test_compose_requires_what_the_server_requires() -> None:
    compose = (ROOT / "deploy" / "compose.env.yml").read_text(encoding="utf-8")
    for row in setting_rows(ROOT):
        if row.get("required") and "server" in row["consumers"]:
            assert f"${{{row['name']}:?" in compose, (
                f"{row['name']} must be ${{NAME:?}} in compose"
            )
