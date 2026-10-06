"""The starter kit, generated and proven.

`rails new` output must be green as generated, and every planted seam defect
must turn the test that guards it red. A guard that stays green on its planted
defect is not a guard, so each defect below is applied to a FRESH copy of the
generated app and the named test must fail -- by exit code 1 (tests failed, not a
collection or usage error) and with the test's own id in a FAILED/ERROR line.

Slow tests skip, saying why, when uv / Postgres / pnpm / chromium are missing.
DATABASE_URL is the ADMIN DSN; the kit only creates and drops `rails_planted_*`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rails.new import TOKEN, KitError, main, new  # noqa: E402

pytestmark = pytest.mark.kit

APP = "kitdemo"
ADMIN_DSN = (
    os.environ.get("DATABASE_URL")
    or "postgresql://postgres:postgres@127.0.0.1:5432/postgres"
)
COPY_IGNORE = shutil.ignore_patterns(
    ".venv", "node_modules", "__pycache__", "dist", ".pytest_cache"
)


def _run(
    argv: list[str], cwd: Path, *, timeout: int = 900
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": ADMIN_DSN,
        "PYTHONUTF8": "1",
        "FORCE_COLOR": "0",
        "NO_COLOR": "1",
    }
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        pytest.skip(f"{name} not found on PATH: not a code failure")
    return path


def _postgres() -> None:
    parts = urlsplit(ADMIN_DSN)
    host, port = parts.hostname or "127.0.0.1", parts.port or 5432
    try:
        with socket.create_connection((host, port), timeout=3):
            return
    except OSError:
        pytest.skip(
            f"Postgres unavailable at {host}:{port}: not a code failure (set DATABASE_URL)"
        )


def _venv_python(app: Path) -> Path:
    return app / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _tail(result: subprocess.CompletedProcess[str], n: int = 4000) -> str:
    return f"exit {result.returncode}\n--- stdout ---\n{result.stdout[-n:]}\n--- stderr ---\n{result.stderr[-n:]}"


# --- generation: fast, stdlib only -----------------------------------------


def test_new_refuses_a_non_empty_destination(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("someone's work", encoding="utf-8")
    with pytest.raises(KitError, match="not an empty directory"):
        new(APP, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep.txt"]


@pytest.mark.parametrize(
    "name", ["Bad Name", "9lives", "contracts", "json", "trailing-"]
)
def test_new_refuses_an_unusable_name(tmp_path: Path, name: str) -> None:
    with pytest.raises(KitError):
        new(name, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_new_substitutes_every_token_in_contents_and_paths(tmp_path: Path) -> None:
    dest = new("my-ledger", tmp_path / "app", rails_ref="v9")
    assert (dest / "src" / "my_ledger" / "roots" / "app.py").is_file()
    leftovers = []
    for path in dest.rglob("*"):
        if TOKEN.search(path.relative_to(dest).as_posix()):
            leftovers.append(f"path {path}")
        elif path.is_file():
            raw = path.read_bytes()  # bytes: read_text would translate CRLF away
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if b"\r\n" in raw:
                leftovers.append(f"CRLF in {path}")
            if found := TOKEN.search(text):
                leftovers.append(f"token in {path}: {found.group(0)}")
    assert not leftovers, "\n".join(leftovers)
    assert json.loads((dest / ".rails-kit.json").read_text(encoding="utf-8")) == {
        "kit_version": "1",
        "rails_ref": "v9",
    }
    assert 'name = "my-ledger"' in (dest / "pyproject.toml").read_text(encoding="utf-8")
    assert "verify-lanes@v9" in (dest / ".github" / "workflows" / "gate.yml").read_text(
        encoding="utf-8"
    )


def test_docs_are_seeded_from_the_plugin_templates_else_the_kit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rails.new as kit

    plugin = tmp_path / "templates"
    plugin.mkdir()
    (plugin / "spec.md").write_text("# <Component> -- living spec\n", encoding="utf-8")
    monkeypatch.setattr(kit, "DOC_TEMPLATES", (plugin,))
    seeded = new("my-ledger", tmp_path / "seeded")
    assert (seeded / "docs" / "spec.md").read_text(
        encoding="utf-8"
    ) == "# My Ledger -- living spec\n"
    # no plugin milestone.md here, so the kit's own is used
    assert "the operator did" in (seeded / "docs" / "milestone.md").read_text(
        encoding="utf-8"
    )

    monkeypatch.setattr(kit, "DOC_TEMPLATES", (tmp_path / "absent",))
    fallback = (new("my-ledger", tmp_path / "fallback") / "docs" / "spec.md").read_text(
        encoding="utf-8"
    )
    for section in (
        "## Scenarios",
        "## Seams",
        "## Failure modes",
        "## Premises",
        "## Amendments",
    ):
        assert section in fallback


def test_main_generates_and_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["ledger", "--dest", str(tmp_path / "ledger")]) == 0
    assert (tmp_path / "ledger" / "src" / "ledger" / "ledger.py").is_file()
    assert main(["ledger", "--dest", str(tmp_path / "ledger")]) == 2
    assert "refusing" in capsys.readouterr().err


def test_generated_lanes_parse_with_the_plugins_reader(tmp_path: Path) -> None:
    from rails import lanes

    config = lanes.load(new(APP, tmp_path / "app") / "lanes.toml")
    assert [lane.name for lane in config.lanes] == [
        "backend",
        "frontend",
        "walk",
        "gen",
    ]
    assert config.lane("gen").always
    picked = lanes.select(config, [f"src/{APP}/ledger.py"])
    assert {lane.name for lane in picked.selected} == {"backend", "walk", "gen"}


# --- the generated backend --------------------------------------------------


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return new(APP, tmp_path_factory.mktemp("kit") / APP)


@pytest.fixture(scope="module")
def app(generated: Path) -> Path:
    uv = _tool("uv")
    _postgres()
    synced = _run([uv, "sync"], generated)
    assert synced.returncode == 0, _tail(synced)
    return generated


def test_generated_backend_suite_is_green(app: Path) -> None:
    result = _run([_tool("uv"), "run", "pytest", "-q", "-rfE"], app)
    assert result.returncode == 0, _tail(result)
    passed = re.search(r"(\d+) passed", result.stdout)
    assert passed and int(passed.group(1)) >= 50, _tail(result)
    assert not re.search(r"\d+ (skipped|xfailed)", result.stdout), (
        "the generated suite must not skip: " + _tail(result)
    )


def test_generated_gen_lane_is_clean(app: Path) -> None:
    _tool("node")
    result = _run(
        [_tool("uv"), "run", "python", "scripts/gen.py", "all", "--check"], app
    )
    assert result.returncode == 0, _tail(result)


Edit = Callable[[str], str]


def replace(old: str, new_text: str) -> Edit:
    def edit(text: str) -> str:
        assert old in text, f"planted anchor not found: {old!r}"
        return text.replace(old, new_text, 1)

    return edit


def within(function: str, old: str, new_text: str) -> Edit:
    """Replace the first `old` after `def <function>(`."""

    def edit(text: str) -> str:
        start = text.index(f"def {function}(")
        at = text.index(old, start)
        return text[:at] + new_text + text[at + len(old) :]

    return edit


def append(block: str) -> Edit:
    return lambda text: text + block


@dataclass(frozen=True)
class Planted:
    id: str
    path: str
    edit: Edit
    test: str  # node id (or file) that must FAIL
    guards: str

    def __str__(self) -> str:
        return self.id


SRC = f"src/{APP}"
BACKEND_DEFECTS = [
    Planted(
        "settings-undeclared-read",
        f"{SRC}/ledger.py",
        append('\nimport os  # noqa: E402\n\nPLANTED = os.environ.get("UNDECLARED")\n'),
        "tests/test_settings_parity.py::test_every_env_read_is_declared",
        "R6 config read outside settings.toml",
    ),
    Planted(
        "contract-retyped-not-regenerated",
        "contracts/wire.py",
        replace("month_total_cents: int", "month_total_cents: float"),
        "tests/test_contracts.py::test_generated_wire_is_current",
        "R7 contract drift",
    ),
    Planted(
        "noop-handler",
        f"{SRC}/events.py",
        append(
            '\n\n@subscribe("entry.recorded")\ndef planted_audit(conn, payload):\n    pass\n'
        ),
        "tests/test_identifier_registry.py::test_no_handler_is_a_noop",
        "R7 a subscriber that does nothing",
    ),
    Planted(
        "null-seam",
        f"{SRC}/roots/app.py",
        replace('"events": bus,', '"events": None,'),
        "tests/test_root_parity.py::test_every_root_composes_its_seams_schedules_and_settings",
        "R4/R5 a seam composed as None",
    ),
    Planted(
        "root-omits-seam",
        f"{SRC}/roots/app.py",
        replace('        "events": bus,\n', ""),
        "tests/test_root_parity.py::test_every_root_composes_its_seams_schedules_and_settings",
        "R5 a root that never composes a declared seam",
    ),
    Planted(
        "wall-clock-read",
        f"{SRC}/ledger.py",
        append(
            "\n\ndef planted_today():\n    from datetime import datetime\n\n    return datetime.now()\n"
        ),
        "tests/test_clock_lint.py::test_no_wall_clock_reads_outside_clock_py",
        "R10 wall clock outside clock.py",
    ),
    Planted(
        "literal-sql-limit",
        f"{SRC}/ledger.py",
        replace("LIMIT %(limit)s", "LIMIT 50"),
        "tests/test_limits_lint.py::test_no_literal_bounds_in_src",
        "R15 limits_gate: an unnamed bound",
    ),
    Planted(
        "cap-without-lock",
        f"{SRC}/ledger.py",
        replace('WHERE id = %s FOR UPDATE"', 'WHERE id = %s"'),
        "tests/test_caps_parallel.py::test_cap_admits_exactly_cap_under_concurrency",
        "R9 an admission cap that races",
    ),
    Planted(
        "month-total-drops-last-day",
        f"{SRC}/ledger.py",
        within(
            "month_total", "occurred_on < %(next)s", "occurred_on < %(next)s::date - 1"
        ),
        "tests/test_surface_parity.py::test_month_total_matches_checker",
        "R15 a surface that disagrees with the oracle",
    ),
    Planted(
        "route-skips-household-check",
        f"{SRC}/routes.py",
        within("list_entries", "    require_household(member, household_id)\n", ""),
        "tests/test_auth_matrix.py::test_route_actor_matrix",
        "R8 a route another household can read",
    ),
    Planted(
        "table-without-rls",
        "migrations/0001_init.sql",
        replace("ALTER TABLE entries ENABLE ROW LEVEL SECURITY;\n", ""),
        "tests/test_rls_unbound.py::test_every_public_table_is_rls_scoped_and_reads_empty_unbound",
        "R9 a table RLS does not scope",
    ),
    Planted(
        "examples-changed-without-hash",
        "concepts.toml",
        replace("expected = 6710", "expected = 6711"),
        "tests/test_concepts.py::test_examples_hash_matches",
        "R15/R16 an examples table edited without its pin",
    ),
]


def _planted_copy(app: Path, defect: Planted, dest: Path) -> Path:
    shutil.copytree(app, dest, ignore=COPY_IGNORE)
    target = dest / defect.path
    before = target.read_text(encoding="utf-8")
    after = defect.edit(before)
    assert after != before, f"{defect.id}: the planted edit changed nothing"
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(after)
    return dest


@pytest.mark.parametrize("defect", BACKEND_DEFECTS, ids=str)
def test_planted_backend_defect_turns_its_guard_red(
    app: Path, defect: Planted, tmp_path: Path
) -> None:
    copy = _planted_copy(app, defect, tmp_path / "planted")
    # The base app's interpreter, run IN the copy: the generated pytest config puts
    # the copy's src/ and root first on sys.path, so the copy's code is what runs.
    result = _run(
        [str(_venv_python(app)), "-m", "pytest", defect.test, "-q", "-rfE"], copy
    )
    assert result.returncode == 1, (
        f"{defect.id} ({defect.guards}): expected exit 1 (tests failed)\n"
        + _tail(result)
    )
    failed = [
        line
        for line in result.stdout.splitlines()
        if line.startswith(("FAILED", "ERROR"))
    ]
    assert any(defect.test in line for line in failed), (
        f"{defect.id}: {defect.test} did not fail\n" + _tail(result)
    )


# --- the generated frontend -------------------------------------------------


@pytest.fixture(scope="module")
def frontend(generated: Path) -> Path:
    _tool("node")
    pnpm = _tool("pnpm")
    root = generated / "frontend"
    installed = _run([pnpm, "install", "--frozen-lockfile"], root)
    assert installed.returncode == 0, _tail(installed)
    return root


def test_generated_frontend_check_is_green(frontend: Path) -> None:
    result = _run([_tool("pnpm"), "run", "check"], frontend)
    assert result.returncode == 0, _tail(result)
    assert re.search(r"Tests\s+\d+ passed", result.stdout), _tail(result)


SCREEN = "src/screens/summary/index.tsx"
STATE_LINE = "  const state = deriveState(me, summary, entries, write);\n"
FRONTEND_DEFECTS = [
    (
        "nullish-default",
        SCREEN,
        replace(STATE_LINE, STATE_LINE + '  const plantedMonth = household ?? "";\n'),
        ["eslint", SCREEN],
        "local/no-nullish-default",
    ),
    (
        "adhoc-format",
        SCREEN,
        replace(
            STATE_LINE, STATE_LINE + "  const plantedText = (1234.5).toFixed(2);\n"
        ),
        ["eslint", SCREEN],
        "local/figure-only",
    ),
    (
        "control-without-id",
        SCREEN,
        replace(
            "<h1>Summary</h1>",
            '<h1>Summary</h1>\n        <button type="button">Planted</button>',
        ),
        ["eslint", SCREEN],
        "local/require-data-control",
    ),
    (
        "raw-fetch",
        SCREEN,
        replace(
            STATE_LINE,
            STATE_LINE + '  const plantedFetch = () => fetch("/api/health");\n',
        ),
        ["eslint", SCREEN],
        "local/no-raw-fetch",
    ),
    (
        "unregistered-concept",
        SCREEN,
        replace(
            "<h1>Summary</h1>",
            '<h1>Summary</h1>\n        <Figure concept="planted_concept" value={1} />',
        ),
        ["tsc", "--noEmit"],
        "planted_concept",
    ),
    (
        "element-never-rendered",
        "elements.json",
        replace(
            '{ "screen": "summary", "id": "summary.add" },',
            '{ "screen": "summary", "id": "summary.add" },\n  { "screen": "summary", "id": "summary.export_csv" },',
        ),
        ["node", "scripts/gen-controls.mjs", "--check"],
        "summary.export_csv",
    ),
]


@pytest.fixture
def restore(frontend: Path) -> Iterator[list[tuple[Path, str]]]:
    """Frontend defects are planted in place (node_modules is not copied) and restored."""
    saved: list[tuple[Path, str]] = []
    yield saved
    for path, text in saved:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)


@pytest.mark.parametrize(
    ("defect", "path", "edit", "argv", "expect"),
    FRONTEND_DEFECTS,
    ids=[d[0] for d in FRONTEND_DEFECTS],
)
def test_planted_frontend_defect_turns_its_guard_red(
    frontend: Path,
    restore: list[tuple[Path, str]],
    defect: str,
    path: str,
    edit: Edit,
    argv: list[str],
    expect: str,
) -> None:
    target = frontend / path
    before = target.read_text(encoding="utf-8")
    restore.append((target, before))
    after = edit(before)
    assert after != before
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(after)
    command = (
        [_tool("node"), *argv[1:]]
        if argv[0] == "node"
        else [_tool("pnpm"), "exec", *argv]
    )
    result = _run(command, frontend)
    assert result.returncode != 0, f"{defect}: the guard stayed green\n" + _tail(result)
    assert expect in result.stdout + result.stderr, (
        f"{defect}: {expect!r} not reported\n" + _tail(result)
    )


# --- the walk ---------------------------------------------------------------


def _chromium(frontend: Path) -> None:
    probe = "const { chromium } = require('playwright'); console.log(chromium.executablePath());"
    found = _run([_tool("node"), "-e", probe], frontend)
    if found.returncode == 0 and Path(found.stdout.strip()).exists():
        return
    if os.environ.get("RAILS_KIT_INSTALL_BROWSERS") == "1":
        installed = _run(
            [_tool("pnpm"), "exec", "playwright", "install", "--with-deps", "chromium"],
            frontend,
        )
        assert installed.returncode == 0, _tail(installed)
        return
    pytest.skip(
        "chromium for playwright is not installed (set RAILS_KIT_INSTALL_BROWSERS=1): not a code failure"
    )


def test_walk_fails_honestly_on_the_first_acceptance_line_only(
    app: Path, frontend: Path
) -> None:
    _chromium(frontend)
    result = _run([_tool("uv"), "run", "python", "scripts/walk.py"], app, timeout=900)
    assert result.returncode == 1, _tail(result)
    receipt = json.loads(result.stdout.strip().splitlines()[-1])
    assert receipt["instrument"] == "walk:planted"
    failed = [s["step"] for s in receipt["steps"] if not s["pass"]]
    assert failed == ["a1"], f"expected only a1 to fail, got {failed}\n" + _tail(result)
    acceptance = json.loads(
        (frontend / "e2e" / "acceptance.json").read_text(encoding="utf-8")
    )
    assert {s["step"] for s in receipt["steps"]} >= {
        line["step"] for line in acceptance
    }
    assert 'step a1 on summary: "Export CSV" not on screen' in result.stdout
