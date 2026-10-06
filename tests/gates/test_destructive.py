"""destructive: apex guard-destructive.sh's five rules, tokenised.

The allowed cases include every false positive apex #38 verified against the
shell original — they are the reason for the rework — and the denied cases
include the false negative it named (a bare `git push --force` on main).
"""

from __future__ import annotations

import subprocess

import pytest

from rails.gates import destructive


@pytest.fixture
def on_main(tmp_path):
    repo = tmp_path / "on-main"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)], check=True, timeout=60
    )
    return repo


@pytest.fixture
def on_feature(tmp_path):
    repo = tmp_path / "on-feature"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "feature/x", str(repo)], check=True, timeout=60
    )
    return repo


@pytest.mark.parametrize(
    "command,label",
    [
        ("rm -rf /", "rm -rf"),
        ("rm -rf ~", "rm -rf"),
        ("rm -rf ~/projects", "rm -rf"),
        ("rm -fr ..", "rm -rf"),
        ('rm -rf "$HOME"', "rm -rf"),
        ("sudo rm -r -f /*", "rm -rf"),
        ("git push --force origin main", "force push"),
        ("git push -f origin master", "force push"),
        ("git push --force origin HEAD:main", "force push"),
        ("git push origin +master", "force push"),
        ("git push --force-with-lease=main:abc origin main", "force push"),
        ("git reset --hard origin/main", "reset --hard"),
        ("git reset --hard origin", "reset --hard"),
        ("rm .env", ".env"),
        ("echo KEY=1 > .env", ".env"),
        ("printf x >> deploy/.env.local", ".env"),
        ("mv .env.example .env", ".env"),
        ("echo x | tee -a .env", ".env"),
        ("git commit --no-verify -m wip", "--no-verify"),
        ("git push --no-verify origin feature", "--no-verify"),
        ("git commit -n -m wip", "--no-verify"),
        ("cd repo && git push -f origin main", "force push"),
    ],
)
def test_bash_destructive_commands_are_denied(reason, command, label):
    assert label in reason(destructive, command)


def test_a_bare_force_push_on_the_default_branch_is_denied(verdict, on_main):
    """apex #38 defect 3: the real disaster passed the shell original."""
    assert verdict(destructive, "git push --force", cwd=on_main) == "deny"
    assert verdict(destructive, "git push -f origin", cwd=on_main) == "deny"


def test_a_bare_force_push_on_a_feature_branch_passes(verdict, on_feature):
    assert verdict(destructive, "git push --force", cwd=on_feature) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        # apex #38, verified false positives of the shell original:
        "git push --force-with-lease origin my-branch && gh pr edit 36 --base main",
        "git push --force origin fix/remain",
        "git push --force origin feature/domain",
        'git push --force origin topic; echo "merged to main"',
        "rm old.txt && cat .env.example",
        "mv a.txt b.txt; grep KEY .env.example",
        "git log --oneline > notes.md  # mentions .env.example",
        # the guard blocked its own bug report: prose about the rules is data
        "gh issue create --body-file - <<'EOF'\ngit push --force origin main\nrm -rf /\nEOF",
        'git commit -m "docs: never use --no-verify or rm -rf ~"',
        # ordinary work
        "rm -rf ./build",
        "rm -rf /tmp/scratch",
        "git push origin main",
        "git push --force origin feature/x",
        "git push --force --dry-run origin main",
        "git reset --hard HEAD~1",
        "cat .env.example > /dev/null",
        "cp .env.example config.txt",
        "git commit -m wip",
    ],
)
def test_ordinary_and_previously_misfired_commands_pass(verdict, command):
    assert verdict(destructive, command) == "allow", command


@pytest.mark.parametrize(
    "command,label",
    [
        ("Remove-Item -Recurse -Force C:\\", "rm -rf"),
        ("Remove-Item ~ -Recurse", "rm -rf"),
        ("rm -r -fo $HOME", "rm -rf"),
        ("ri -Recurse -Path $env:USERPROFILE\\Documents", "rm -rf"),
        ("Remove-Item .. -Recurse -Force", "rm -rf"),
        ("git push --force origin main", "force push"),
        ("git reset --hard origin/master", "reset --hard"),
        ("Set-Content .env 'KEY=1'", ".env"),
        ("'KEY=1' | Out-File -FilePath deploy\\.env.prod", ".env"),
        ("Remove-Item .env", ".env"),
        ("Add-Content -Path .env -Value x", ".env"),
        ("git commit --no-verify -m wip", "--no-verify"),
    ],
)
def test_powershell_destructive_commands_are_denied(reason, command, label):
    assert label in reason(destructive, command, tool="PowerShell")


@pytest.mark.parametrize(
    "command",
    [
        "Remove-Item -Recurse -Force .\\build",
        "Remove-Item C:\\Users\\dev\\repo\\dist -Recurse",
        "Get-Content .env.example",
        "git commit -m 'never --no-verify'",
        "Write-Output 'Remove-Item -Recurse C:\\'",
    ],
)
def test_powershell_ordinary_commands_pass(verdict, command):
    assert verdict(destructive, command, tool="PowerShell") == "allow", command


def test_the_message_keeps_the_original_shape(reason):
    text = reason(destructive, "rm -rf /")
    assert text.startswith("BLOCKED: rm -rf targeting root, home, or parent directory")
    assert "Command: rm -rf /" in text
    assert "Ask the user to confirm before proceeding" in text


def test_only_the_operator_environment_overrides(verdict, monkeypatch):
    assert verdict(destructive, "RAILS_DESTRUCTIVE_OK=1 rm -rf /") == "deny"
    monkeypatch.setenv("RAILS_DESTRUCTIVE_OK", "1")
    assert verdict(destructive, "rm -rf /") == "allow"


def test_head_branch_reads_a_linked_worktree(tmp_path, on_main):
    subprocess.run(
        ["git", "-C", str(on_main), "commit", "--allow-empty", "-q", "-m", "x"],
        check=True,
        timeout=60,
        env={
            **__import__("os").environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        },
    )
    linked = tmp_path / "linked"
    subprocess.run(
        ["git", "-C", str(on_main), "worktree", "add", "-q", "-b", "side", str(linked)],
        check=True,
        timeout=60,
    )
    assert destructive.head_branch(linked) == "side"
    assert destructive.head_branch(on_main) == "main"
