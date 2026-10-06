"""The gate registry (hooks/gates.toml) against the modules and planted defects it names.

A row earns its place with a cite, a planted defect, and a false-positive count.
This file is what makes the planted defect mean something: every row whose
``planted`` is a payload file is fed to the REAL dispatcher with the row forced
to enforce mode, and the dispatcher must refuse it. A gate that silently
stopped matching therefore fails here even while its own unit tests (which
call ``check`` directly) still pass — and a row whose module went missing is
caught twice: by the import check and by its planted payload.

``planted`` takes one of two forms:

* ``tests/planted/<name>.json`` — ``{"event", "payload", "expect", "fixture"?}``.
  ``fixture`` is optional harness setup the payload needs to be refusable:
  ``files`` (name -> JSON, written into a tmp dir), ``env`` (values may say
  ``{tmp}``), ``git_repo: true`` (the payload's ``cwd`` becomes a fresh
  ``git init`` repo), ``store`` (name -> JSON, written into that repo's leaf
  dir in the rails store);
* ``tests/<file>.py::<test>`` — a pytest node id whose test plants the defect
  itself (the gate needs state a payload cannot carry). Asserted to exist; the
  dispatcher check is that test's job.

Rows whose only event is ``git:pre-push`` run in the git hook, never in the
dispatcher; their ``prepush`` module is an anchor and is exempt from the
import check.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import importlib
import importlib.util
import io
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

from rails import dispatch, store
from rails.dispatch import GateRow, load_registry
from rails.hookio import Event

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "hooks" / "gates.toml"
GATES_DIR = ROOT / "rails" / "gates"

REQUIRED = (
    "name",
    "module",
    "events",
    "kind",
    "class",
    "mode",
    "cites",
    "planted",
    "fp_count",
    "fp_measured_on",
)

NODE_ID = re.compile(r"^(?P<file>tests/[\w/.-]+\.py)::(?P<rest>[\w:\[\]-]+)$")


@pytest.fixture(autouse=True)
def no_inherited_overrides(monkeypatch):
    """An exported override would make every planted refusal pass vacuously."""
    for name in list(os.environ):
        upper = name.upper()
        if upper.startswith(("JARVIS_", "RAILS_")) and (
            upper.endswith("_OK") or upper.endswith("_PR_LOOKUP_FIXTURE")
        ):
            monkeypatch.delenv(name, raising=False)


def _raw_rows() -> list[dict]:
    with open(REGISTRY, "rb") as handle:
        return tomllib.load(handle)["gate"]


def _rows() -> list[GateRow]:
    return load_registry(REGISTRY)


def _git_hook_only(raw: dict) -> bool:
    return all(str(e).startswith("git:") for e in raw.get("events", []))


def _module_exists(module: str) -> bool:
    return importlib.util.find_spec(f"rails.gates.{module}") is not None


# --- (a) modules and rows match ---------------------------------------------------


def test_every_gate_module_has_a_row():
    modules = {p.stem for p in GATES_DIR.glob("*.py") if p.stem != "__init__"}
    named = {row.module for row in _rows()}
    assert modules, "no gate modules found: the glob is wrong, not the registry"
    assert sorted(modules - named) == [], "gate modules with no registry row never run"


@pytest.mark.parametrize("raw", _raw_rows(), ids=lambda r: r["name"])
def test_every_row_module_imports_and_exposes_check(raw):
    module_name = raw.get("module", raw["name"])
    if _git_hook_only(raw) and module_name == "prepush":
        pytest.skip("git-hook anchor: never dispatched")
    module = importlib.import_module(f"rails.gates.{module_name}")
    assert callable(getattr(module, "check", None)), f"{module_name} has no check()"


def test_row_names_are_unique():
    names = [raw["name"] for raw in _raw_rows()]
    assert len(names) == len(set(names))


# --- (b) every row carries its evidence -------------------------------------------


@pytest.mark.parametrize("raw", _raw_rows(), ids=lambda r: r["name"])
def test_every_row_has_the_required_fields(raw):
    missing = [key for key in REQUIRED if key not in raw]
    assert missing == [], f"{raw['name']} is missing {missing}"
    assert raw["cites"], f"{raw['name']} cites nothing"
    assert all(str(c).strip() for c in raw["cites"])
    assert raw["mode"] in ("enforce", "shadow")
    assert raw["class"] in ("lockout", "friction")
    assert isinstance(raw["fp_count"], int) and raw["fp_count"] >= 0
    assert str(raw["fp_measured_on"]).strip()
    if raw.get("shadow_until"):
        _dt.date.fromisoformat(raw["shadow_until"])


# --- (c) the planted defect is refused by the real dispatcher ---------------------


def _apply_fixture(payload: dict, fixture: dict, tmp: Path, monkeypatch) -> None:
    for name, value in (fixture.get("files") or {}).items():
        (tmp / name).write_text(json.dumps(value), encoding="utf-8")
    for key, value in (fixture.get("env") or {}).items():
        monkeypatch.setenv(key, str(value).replace("{tmp}", str(tmp)))
    if fixture.get("git_repo"):
        repo = tmp / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=60)
        payload["cwd"] = str(repo)
    if fixture.get("store"):
        found = store.find_repo(Path(payload.get("cwd") or "."))
        assert found is not None, "fixture.store needs a payload cwd inside a git repo"
        for name, value in fixture["store"].items():
            store.write_json(found.leaf_dir / name, value)


@pytest.mark.parametrize(
    "raw", [r for r in _raw_rows() if r.get("planted")], ids=lambda r: r["name"]
)
def test_the_planted_defect_is_refused(raw, tmp_path, monkeypatch):
    planted = str(raw["planted"])
    module_name = raw.get("module", raw["name"])
    node = NODE_ID.match(planted)
    if node:
        path = ROOT / node.group("file")
        assert path.is_file(), f"{raw['name']}: planted test file {path} is missing"
        function = node.group("rest").split("::")[-1].split("[")[0]
        source = path.read_text(encoding="utf-8")
        assert re.search(rf"^\s*def {re.escape(function)}\(", source, re.M), (
            f"{raw['name']}: {path.name} defines no {function}"
        )
        return  # that test plants and checks the defect itself
    path = ROOT / planted
    if not path.is_file():
        if not _module_exists(module_name):
            pytest.skip(f"{raw['name']}: module and planted file both not written yet")
        pytest.fail(f"{raw['name']}: planted file {planted} is missing")
    case = json.loads(path.read_text(encoding="utf-8"))
    payload = dict(case["payload"])
    _apply_fixture(payload, case.get("fixture") or {}, tmp_path, monkeypatch)
    event = Event(
        name=case.get("event", payload.get("hook_event_name", "")), payload=payload
    )

    row = next(r for r in _rows() if r.name == raw["name"])
    forced = dataclasses.replace(row, mode="enforce", shadow_until="")
    outcome = dispatch.dispatch(event, rows=[forced])

    assert not any("missing; unguarded" in n for n in outcome.notices), outcome.notices
    assert not any("crashed" in n for n in outcome.notices), outcome.notices
    expect = case.get("expect", "deny")
    if event.name == "PreToolUse":
        assert expect == "deny"
        assert outcome.denies, f"{raw['name']} did not refuse its own planted defect"
        rendered = json.loads(outcome.render())
        assert rendered["hookSpecificOutput"]["permissionDecision"] == "deny"
    else:
        assert expect == "block"
        assert outcome.blocks, f"{raw['name']} did not block its own planted defect"


def test_planted_payloads_look_like_the_harness_sent_them():
    for path in sorted((ROOT / "tests" / "planted").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        payload = case["payload"]
        for key in ("hook_event_name", "tool_name", "tool_input", "session_id", "cwd"):
            assert key in payload, f"{path.name} lacks {key}"
        assert payload["hook_event_name"] == case["event"]


def test_planted_payloads_cover_powershell():
    tools = [
        json.loads(p.read_text(encoding="utf-8"))["payload"]["tool_name"]
        for p in (ROOT / "tests" / "planted").glob("*.json")
    ]
    assert tools.count("PowerShell") >= 3


# --- (d) a missing module is loud, never fatal ------------------------------------

GHOST = GateRow(
    name="ghost",
    module="no_such_gate_module_xyz",
    events=["PreToolUse"],
    tools=["Bash"],
)


def _bash_event(command: str, cwd: Path | str = ".") -> Event:
    return Event(
        "PreToolUse",
        {
            "hook_event_name": "PreToolUse",
            "session_id": "registry",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(cwd),
        },
    )


def test_a_missing_module_yields_the_unguarded_notice():
    outcome = dispatch.dispatch(_bash_event("git status"), rows=[GHOST])
    assert outcome.notices == ["RAILS: gate ghost missing; unguarded"]
    assert outcome.denies == []
    rendered = json.loads(outcome.render())
    assert "permissionDecision" not in rendered["hookSpecificOutput"]
    assert rendered["hookSpecificOutput"]["additionalContext"] == (
        "RAILS: gate ghost missing; unguarded"
    )


def test_a_missing_module_exits_zero_through_main(monkeypatch, capsys):
    monkeypatch.setattr(dispatch, "load_registry", lambda *a, **k: [GHOST])
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "registry",
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
        "cwd": ".",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert dispatch.main(["rails_hook.py", "PreToolUse"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (
        "RAILS: gate ghost missing; unguarded"
        in out["hookSpecificOutput"]["additionalContext"]
    )


# --- (e) shadow mode logs would-deny and refuses nothing --------------------------


def test_a_shadowed_row_logs_would_deny_and_refuses_nothing(repo):
    stash_row = next(r for r in _rows() if r.name == "stash")
    future = (_dt.date.today() + _dt.timedelta(days=7)).isoformat()
    shadowed = dataclasses.replace(stash_row, mode="enforce", shadow_until=future)

    outcome = dispatch.dispatch(_bash_event("git stash", cwd=repo), rows=[shadowed])

    assert outcome.denies == []
    assert outcome.render() == ""
    found = store.find_repo(repo)
    assert found is not None
    assert str(store.data_root()) in str(found.dir), "the store must be the tmp one"
    lines = store.read_jsonl(found.dir / "firings.jsonl")
    assert [(r["gate"], r["verdict"]) for r in lines] == [("stash", "would-deny")]
    assert "git stash" not in json.dumps(lines), "the command text must never persist"


def test_the_same_row_enforced_refuses(repo):
    stash_row = next(r for r in _rows() if r.name == "stash")
    enforced = dataclasses.replace(stash_row, mode="enforce", shadow_until="")
    outcome = dispatch.dispatch(_bash_event("git stash", cwd=repo), rows=[enforced])
    assert outcome.denies
