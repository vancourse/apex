"""secret_env: cases ported from jarvis ci/test_secret_env_gate.py, plus PowerShell."""

from __future__ import annotations

import pytest

from rails.gates import secret_env

#: Verbatim from the 2026-08-13 transcript; note the redaction filter that
#: was present, did not match, and did not stop the value printing.
OBSERVED_LEAK = (
    "docker exec dev-jarvis-fleet-1 sh -c 'env | grep -i studio "
    '| sed "s/=.*SECRET.*/=<redacted>/" \''
)


def test_denies_the_observed_leak(verdict):
    assert 'sed "s/=.*SECRET.*/=<redacted>/"' in OBSERVED_LEAK
    assert verdict(secret_env, OBSERVED_LEAK) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "env",
        "printenv",
        "env | grep -i studio",
        "docker exec c sh -c 'env'",
        "docker exec c sh -c 'env | grep -i key'",
        "docker inspect dev-jarvis-fleet-1",
        "docker container inspect x",
        "docker inspect --format '{{.Config.Env}}' x",
        "cat .env",
        "cat deploy/fleet/.env.dev",
        "head -50 .env.local",
        "python -c 'import os; print(os.environ)'",
        "node -e 'console.log(process.env)'",
        "cat /proc/1/environ",
    ],
)
def test_denies_every_dumping_shape(verdict, command):
    assert verdict(secret_env, command) == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "env | cut -d= -f1",
        "docker exec c sh -c 'env | cut -d= -f1'",
        "env | cut -d'=' -f1 | sort",
        "env | awk -F= '{print $1}'",
        "env | sed 's/=.*//'",
        "docker exec c sh -c 'env | grep -oE \"^STUDIO\"'",
        "docker inspect --format '{{.State.Status}}' x",
        "compgen -v",
        "env DATABASE_URL=postgres://x uv run pytest -q",
        "git status",
        "uv run pytest -q ci/test_secret_env_gate.py",
        "curl -s https://example.invalid/readyz",
        "grep -rn 'os.environ.get' apps/",
        "cat README.md",
        "docker ps --filter name=dev-jarvis",
    ],
)
def test_allows_safe_and_ordinary_commands(verdict, command):
    assert verdict(secret_env, command) == "allow", command


@pytest.mark.parametrize(
    "command,expected",
    [
        ('env | grep -oE "^STUDIO"', "allow"),
        ('env | grep -oE "^STUDIO.*=.*"', "deny"),
        ('env | grep -o "^A=B"', "deny"),
    ],
)
def test_name_only_grep_is_distinguished_from_a_value_emitting_one(
    verdict, command, expected
):
    assert verdict(secret_env, command) == expected


def test_prose_mentioning_the_env_api_is_not_a_dump(verdict):
    commit = (
        "git commit -F - <<'EOF'\n"
        "feat(hooks): refuse a command that prints environment values\n\n"
        "Also covered: bulk os.environ / process.env dumps. Narrowed access --\n"
        'os.environ.get("X") -- stays allowed.\n'
        "EOF"
    )
    assert verdict(secret_env, commit) == "allow"
    assert verdict(secret_env, "grep -rn 'os.environ' apps/ | head") == "allow"
    assert verdict(secret_env, 'echo "process.env is the node equivalent"') == "allow"


def test_narrowed_environ_access_is_not_a_dump(verdict):
    assert (
        verdict(secret_env, "python -c 'import os; print(os.environ.get(\"HOME\"))'")
        == "allow"
    )


def test_a_very_long_command_does_not_hang(verdict):
    assert verdict(secret_env, "echo " + "a" * 20000) == "allow"


# --- PowerShell ------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "Get-ChildItem env:",
        "gci env: | Sort-Object Name",
        "ls Env:\\",
        "dir env:*KEY*",
        "Get-Item -Path env:*",
        "[Environment]::GetEnvironmentVariables()",
        "[System.Environment]::GetEnvironmentVariables() | Format-List",
        "cmd /c set",
        "Get-Content .env",
        'Get-Content ".env.dev"',
        "gc deploy\\fleet\\.env.prod",
        "type .env",
        "docker inspect dev-jarvis-fleet-1",
    ],
)
def test_powershell_dumps_are_denied(verdict, command):
    assert verdict(secret_env, command, tool="PowerShell") == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "Get-ChildItem env: | Select-Object -ExpandProperty Name",
        "(Get-ChildItem env:).Name",
        "Get-ChildItem env: -Name",
        "[Environment]::GetEnvironmentVariables().Keys",
        "Get-ChildItem env:PATH",
        "Write-Output $env:USERPROFILE",
        "Get-ChildItem C:\\src",
        "Get-Content README.md",
        "cmd /c setx FOO bar",
    ],
)
def test_powershell_names_and_single_reads_pass(verdict, command):
    assert verdict(secret_env, command, tool="PowerShell") == "allow", command


# --- overrides ---------------------------------------------------------------------


def test_override_as_documented_allows(verdict):
    assert verdict(secret_env, "env") == "deny"
    assert verdict(secret_env, "JARVIS_ENV_DUMP_OK=1 env") == "allow"
    assert verdict(secret_env, "RAILS_ENV_DUMP_OK=1 env") == "allow"


def test_powershell_override_allows(verdict):
    command = "$env:JARVIS_ENV_DUMP_OK = '1'; Get-ChildItem env:"
    assert verdict(secret_env, command, tool="PowerShell") == "allow"


def test_empty_override_does_not_allow(verdict):
    assert verdict(secret_env, "JARVIS_ENV_DUMP_OK= env") == "deny"
    assert (
        verdict(secret_env, "$env:RAILS_ENV_DUMP_OK=''; gci env:", tool="PowerShell")
        == "deny"
    )


def test_non_shell_tools_are_untouched(verdict):
    assert verdict(secret_env, "env", tool="Read") == "allow"
