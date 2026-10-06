"""secret_file_touch: cases ported from jarvis ci/test_secret_file_touch_gate.py."""

from __future__ import annotations

import pytest

from rails.gates import secret_file_touch

#: Verbatim from 2026-09-15: the two names-only commands that preceded the
#: harness surfacing `.env.dev` in full, unprompted.
OBSERVED_LEAK_PRECURSORS = (
    "cut -d= -f1 deploy/fleet/.env.dev",
    'grep "^OUTLOOK_" deploy/fleet/.env.dev',
)


@pytest.mark.parametrize("command", OBSERVED_LEAK_PRECURSORS)
def test_denies_the_observed_leak_precursors(verdict, command):
    assert verdict(secret_file_touch, command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "cat deploy/fleet/.env.dev",
        "cat deploy/fleet/.env.prod",
        "grep API_KEY deploy/fleet/.env.dev",
        "wc -l deploy/fleet/.env.dev",
        "cut -d= -f1 .env.dev",
        "cat deploy/fleet/.op-token.dev",
        "cat deploy/fleet/.delivery.dev",
        "cat deploy/fleet/.delivery.prod",
    ],
)
def test_denies_every_reference_shape_in_bash(verdict, command):
    assert verdict(secret_file_touch, command) == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "Get-Content deploy\\fleet\\.op-token.dev",
        "notepad deploy\\fleet\\.env.dev",
        "type deploy\\fleet\\.env.dev",
        'Get-Content "C:\\Users\\dev\\repo\\deploy\\fleet\\.env.dev"',
        "gc .env | Select-Object -First 3",
        "Select-String -Path deploy\\fleet\\.env.dev -Pattern KEY",
        "Copy-Item deploy\\fleet\\.env.prod C:\\tmp\\x",
    ],
)
def test_denies_every_reference_shape_in_powershell(verdict, command):
    assert verdict(secret_file_touch, command, tool="PowerShell") == "deny", command


@pytest.mark.parametrize(
    "tool,key,value",
    [
        ("Read", "file_path", "deploy/fleet/.env.dev"),
        ("Read", "file_path", "C:\\Users\\dev\\repo\\deploy\\fleet\\.env.dev"),
        ("Grep", "path", "deploy/fleet/.env.dev"),
        ("Glob", "path", "deploy/fleet/.env.dev"),
        ("Edit", "file_path", "C:\\Users\\dev\\repo\\.env"),
        ("Write", "file_path", "deploy/fleet/.op-token.prod"),
        ("MultiEdit", "file_path", "deploy/fleet/.delivery.prod"),
    ],
)
def test_denies_the_path_tools(verdict, tool, key, value):
    assert verdict(secret_file_touch, tool=tool, **{key: value}) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "cat README.md",
        "cat deploy/fleet/.env.example",
        "cat deploy/fleet/.env.dev.example",
        "grep -rn 'os.environ.get' apps/",
        "grep -rn 'JARVIS_ENVIRONMENT' apps/jarvis/src",
        "docker ps --filter name=dev-jarvis",
        "uv run pytest -q ci/test_secret_file_touch_gate.py",
        "fleet.py up dev --sync",
        ".\\scripts\\sync-dev.ps1",
        ".\\scripts\\run.ps1 up dev",
        "echo 'reads config from a .env file, see deploy/fleet/'",
        "cat something.environment.json",
        "cat my-envelope.txt",
    ],
)
def test_allows_safe_and_ordinary_commands(verdict, command):
    assert verdict(secret_file_touch, command) == "allow", command
    assert verdict(secret_file_touch, command, tool="PowerShell") == "allow", command


def test_allows_unrelated_paths_and_unscoped_searches(verdict):
    assert (
        verdict(secret_file_touch, tool="Read", file_path="apps/purser/src/cli.py")
        == "allow"
    )
    assert (
        verdict(secret_file_touch, tool="Read", file_path="deploy/fleet/.env.example")
        == "allow"
    )
    assert verdict(secret_file_touch, tool="Grep", path="apps/purser") == "allow"
    assert (
        verdict(secret_file_touch, tool="Grep", pattern="OUTLOOK_CLIENT_ID") == "allow"
    )
    assert (
        verdict(secret_file_touch, tool="Edit", file_path="src/environment.py")
        == "allow"
    )


def test_override_as_documented_allows(verdict):
    command = "cat deploy/fleet/.env.dev"
    assert verdict(secret_file_touch, command) == "deny"
    assert (
        verdict(secret_file_touch, f"JARVIS_SECRET_FILE_TOUCH_OK=1 {command}")
        == "allow"
    )
    assert (
        verdict(secret_file_touch, f"RAILS_SECRET_FILE_TOUCH_OK=1 {command}") == "allow"
    )


def test_powershell_override_allows(verdict):
    command = "$env:JARVIS_SECRET_FILE_TOUCH_OK=1; Get-Content deploy\\fleet\\.env.dev"
    assert verdict(secret_file_touch, command, tool="PowerShell") == "allow"


def test_empty_override_does_not_allow(verdict):
    command = "JARVIS_SECRET_FILE_TOUCH_OK= cat deploy/fleet/.env.dev"
    assert verdict(secret_file_touch, command) == "deny"


def test_no_override_for_path_tools(verdict, monkeypatch):
    """The escape hatch lives in one place (the shells); the operator's own
    environment does not open the path tools either."""
    monkeypatch.setenv("JARVIS_SECRET_FILE_TOUCH_OK", "1")
    assert verdict(secret_file_touch, tool="Read", file_path=".env.dev") == "deny"


def test_a_very_long_command_does_not_hang(verdict):
    assert verdict(secret_file_touch, "echo " + "a" * 20000) == "allow"
