"""heredoc_write: cases ported from jarvis ci/test_heredoc_write_gate.py, plus
the PowerShell expanding here-string."""

from __future__ import annotations

import pytest

from rails.gates import heredoc_write

OBSERVED_SHAPE = 'cat > parser.py <<EOF\nPATTERN = re.compile(r"\\\\d+\\\\s*USD")\nEOF'
OBSERVED_STDIN_SHAPE = "gh pr create --body-file - <<EOF\n## What this does\n\nFixes `\\\\d` handling.\nEOF"


def test_denies_the_observed_shapes(verdict):
    assert verdict(heredoc_write, OBSERVED_SHAPE) == "deny"
    assert ">" not in OBSERVED_STDIN_SHAPE.splitlines()[0]
    assert verdict(heredoc_write, OBSERVED_STDIN_SHAPE) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "cat > f.py <<EOF\nbody\nEOF",
        "cat >> f.py <<EOF\nbody\nEOF",
        "cat << EOF > f.py\nbody\nEOF",
        "cat <<-EOF\nbody\nEOF",
        "cat <<EOF | tee out.txt\nbody\nEOF",
        "python <<EOF\nprint(1)\nEOF",
        "psql <<EOF\nSELECT 1;\nEOF",
        "cat <<EOF\nbody\nEOF",
        "cat <<_MARKER\nbody\n_MARKER",
        "cat > a.txt <<'EOF'\nx\nEOF\ncat > b.txt <<EOF\ny\nEOF",
    ],
)
def test_denies_every_unquoted_shape(verdict, command):
    assert verdict(heredoc_write, command) == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "cat > f.py <<'EOF'\nbody\nEOF",
        'cat > f.py <<"EOF"\nbody\nEOF',
        "cat > f.py <<\\EOF\nbody\nEOF",
        "cat <<-'EOF'\nbody\nEOF",
        "gh pr create --body-file - <<'EOF'\n## What this does\n\nx\nEOF",
        'python -c "print(1 << 3)"',
        "echo 'shift left: a << b'",
        "grep -rn '<<EOF' docs/",
        "echo 'see <<EOF in the docs'",
        "grep -rn '<<EOF' docs/\ngit status",
        "git status",
        "uv run pytest -q ci/test_heredoc_write_gate.py",
        "cat README.md",
    ],
)
def test_allows_quoted_and_ordinary_commands(verdict, command):
    assert verdict(heredoc_write, command) == "allow", command


def test_the_gates_own_commit_message_is_not_denied(verdict):
    commit = (
        "git commit -F - <<'EOF'\n"
        "feat(hooks): refuse a heredoc whose delimiter is unquoted\n\n"
        "`cat > f <<EOF` expands the body; `cat > f <<'EOF'` does not.\n"
        "EOF"
    )
    assert verdict(heredoc_write, commit) == "allow"


def test_an_unterminated_heredoc_fails_open(verdict):
    assert (
        verdict(heredoc_write, "cat > f.py <<EOF\nbody with no terminator") == "allow"
    )


def test_many_lines_do_not_hang(verdict):
    command = "\n".join(f"echo line {i}" for i in range(5000))
    assert verdict(heredoc_write, command) == "allow"


def test_message_names_the_write_tool_when_a_file_is_the_target(reason):
    text = reason(heredoc_write, "cat > parser.py <<EOF\nbody\nEOF")
    assert "Write tool" in text and "parser.py" in text


def test_message_names_the_quoting_fix_when_no_file_is_written(reason):
    text = reason(heredoc_write, "python <<EOF\nprint(1)\nEOF")
    assert "<<'EOF'" in text and "Write tool" not in text


def test_message_reports_the_delimiter_actually_used(reason):
    assert "<<'MARKER'" in reason(heredoc_write, "cat <<MARKER\nbody\nMARKER")


# --- PowerShell ------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        '@"\nPATTERN = re.compile(r"(\\d+)\\s*$1")\n"@ | Set-Content parser.py',
        'Set-Content -Path run.ps1 -Value @"\nWrite-Output $env:PATH\n"@',
        'gh pr create --body @"\nCost: `$5 and $total\n"@',
        '$body = @"\nsee $(Get-Date)\n"@\nOut-File -FilePath notes.md -InputObject $body',
    ],
)
def test_powershell_expanding_here_string_is_denied(verdict, command):
    assert verdict(heredoc_write, command, tool="PowerShell") == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "@'\nPATTERN = re.compile(r\"(\\d+)\\s*$1\")\n'@ | Set-Content parser.py",
        # nothing PowerShell would rewrite: arrives byte-for-byte
        '@"\nplain text, C:\\path\\to\\file\n"@ | Set-Content notes.txt',
        # a literal here-string whose BODY discusses the trap
        "git commit -m @'\nnever write @\"\nwith $vars\n\"@ here\n'@",
        # unterminated: not a here-string
        'Write-Output @"\n$x never closes',
        "git status",
    ],
)
def test_powershell_literal_and_harmless_here_strings_pass(verdict, command):
    assert verdict(heredoc_write, command, tool="PowerShell") == "allow", command


def test_powershell_message_names_the_target_and_the_literal_form(reason):
    text = reason(
        heredoc_write,
        '@"\n$1\n"@ | Set-Content parser.py',
        tool="PowerShell",
    )
    assert "parser.py" in text and "Write tool" in text and "@'" in text
    no_file = reason(heredoc_write, 'gh pr create --body @"\n$x\n"@', tool="PowerShell")
    assert "Write tool" not in no_file and "@'" in no_file


# --- overrides ---------------------------------------------------------------------


def test_override_as_documented_allows(verdict):
    assert verdict(heredoc_write, f"JARVIS_HEREDOC_OK=1 {OBSERVED_SHAPE}") == "allow"
    assert verdict(heredoc_write, f"RAILS_HEREDOC_OK=1 {OBSERVED_SHAPE}") == "allow"


def test_powershell_override_allows(verdict):
    command = '$env:JARVIS_HEREDOC_OK=1; gh pr create --body @"\n$x\n"@'
    assert verdict(heredoc_write, command, tool="PowerShell") == "allow"


def test_empty_override_does_not_allow(verdict):
    assert verdict(heredoc_write, f"JARVIS_HEREDOC_OK= {OBSERVED_SHAPE}") == "deny"


def test_the_denial_message_documents_the_override_that_works(reason):
    assert "JARVIS_HEREDOC_OK=1" in reason(heredoc_write, OBSERVED_SHAPE)


def test_non_shell_tools_are_untouched(verdict):
    assert verdict(heredoc_write, OBSERVED_SHAPE, tool="Read") == "allow"
