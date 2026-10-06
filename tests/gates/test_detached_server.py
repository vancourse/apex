"""detached_server: cases ported from jarvis ci/test_detached_server_gate.py,
plus the PowerShell detachments."""

from __future__ import annotations

import pytest

from rails.gates import detached_server

OBSERVED_LEAK = (
    "cd docs/status && nohup python -m http.server 8791 --bind 127.0.0.1 "
    ">/dev/null 2>&1 &\nsleep 2\ncurl -s http://127.0.0.1:8791/board.html"
)


def test_denies_the_observed_leak(verdict):
    assert verdict(detached_server, OBSERVED_LEAK) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "nohup python -m http.server 8791 &",
        "python3 -m http.server 9000 --bind 127.0.0.1 &",
        "nohup python3 -m http.server 5180 --directory docs >/dev/null 2>&1 &",
        "cd docs && nohup py -m http.server 8080 &",
        # The original's quote-blind split still sees a server inside sh -c.
        "sh -c 'python -m http.server 8000 &'",
    ],
)
def test_denies_every_detached_shape(verdict, command):
    assert verdict(detached_server, command) == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "python -m http.server 8000 && echo done",
        "python -m http.server 8000",
        "python -m http.server 8000 --bind 127.0.0.1",
        "bash scripts/board.sh --no-open",
        "uv run python docs/status/serve_board.py --mount-path /docs",
        "git status --porcelain",
        "pytest ci/ -q",
        "grep -rn 'http.server' docs/",
    ],
)
def test_allows_everything_else(verdict, command):
    assert verdict(detached_server, command) == "allow", command


@pytest.mark.parametrize(
    "command",
    [
        "Start-Process python -ArgumentList '-m','http.server','8791' -WindowStyle Hidden",
        'Start-Process -FilePath py -ArgumentList "-m http.server 8080"',
        "start python3 '-m http.server 9000'",
        "Start-Job { python -m http.server 8000 }",
        "python -m http.server 8000 &",
        "cmd /c start python -m http.server 8000",
        "Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
        "-Arguments @{CommandLine='python -m http.server 8000'}",
        "Set-Location docs; Start-Process python.exe '-m http.server 5180'",
    ],
)
def test_powershell_detachments_are_denied(verdict, command):
    assert verdict(detached_server, command, tool="PowerShell") == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "python -m http.server 8000",
        "Start-Process python -ArgumentList '-m','http.server' -Wait",
        "Start-Process notepad",
        "Start-Job { pytest -q }",
        "Select-String -Path docs\\*.md -Pattern 'http.server'",
    ],
)
def test_powershell_foreground_and_unrelated_pass(verdict, command):
    assert verdict(detached_server, command, tool="PowerShell") == "allow", command


def test_powershell_message_carries_the_reaping_note(reason):
    text = reason(
        detached_server, "Start-Process python '-m http.server'", tool="PowerShell"
    )
    assert "reaped" in text and "$env:JARVIS_DETACHED_SERVER_OK=1;" in text


def test_override_env_var_allows(verdict, monkeypatch):
    monkeypatch.setenv("JARVIS_DETACHED_SERVER_OK", "1")
    assert verdict(detached_server, OBSERVED_LEAK) == "allow"


def test_override_as_documented_allows(verdict):
    assert (
        verdict(detached_server, f"JARVIS_DETACHED_SERVER_OK=1 {OBSERVED_LEAK}")
        == "allow"
    )
    assert (
        verdict(detached_server, f"RAILS_DETACHED_SERVER_OK=1 {OBSERVED_LEAK}")
        == "allow"
    )


def test_powershell_override_allows(verdict):
    command = "$env:RAILS_DETACHED_SERVER_OK=1; Start-Process python '-m http.server'"
    assert verdict(detached_server, command, tool="PowerShell") == "allow"


def test_override_needs_a_value(verdict):
    assert (
        verdict(detached_server, f"JARVIS_DETACHED_SERVER_OK= {OBSERVED_LEAK}")
        == "deny"
    )


def test_ignores_other_tools(verdict):
    assert verdict(detached_server, OBSERVED_LEAK, tool="Write") == "allow"
