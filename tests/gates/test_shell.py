"""rails.shell: what a gate may read in a command line, for both shells.

The property every gate leans on is that scrubbing never moves an offset, so a
match in the scrubbed text is a position in the original. Every case asserts
the length first.
"""

from __future__ import annotations

import pytest

from rails.shell import scrub, scrubbed_segments, segments, words


def _scrub(command: str, shell: str) -> str:
    out = scrub(command, shell)
    assert len(out) == len(command)
    return out


# --- bash ----------------------------------------------------------------------


def test_bash_quoted_spans_are_blank_and_the_length_holds():
    command = "git commit -m \"never git stash\" && echo 'git stash' $'git\\'s stash'"
    out = _scrub(command, "bash")
    assert "stash" not in out
    assert out.startswith("git commit -m ")
    assert "&& echo" in out


def test_bash_quoted_separators_do_not_split():
    command = 'git commit -m "a; b && c || d & e" ; git status'
    assert segments(command, "bash") == [
        'git commit -m "a; b && c || d & e"',
        "git status",
    ]


def test_bash_splits_on_every_top_level_separator():
    command = "a; b && c || d & e\nf | g"
    assert segments(command, "bash") == ["a", "b", "c", "d &", "e", "f | g"]


def test_bash_redirections_are_not_background_separators():
    command = "pytest 2>&1 | tail; a &> log; b |& c; d >&2"
    assert segments(command, "bash") == [
        "pytest 2>&1 | tail",
        "a &> log",
        "b |& c",
        "d >&2",
    ]


def test_bash_heredoc_body_is_blank_and_never_a_statement():
    command = "git commit -F - <<'EOF'\nfix; git stash && rm -rf /\nEOF\ngit push"
    out = _scrub(command, "bash")
    assert "stash" not in out and "rm -rf" not in out
    assert segments(command, "bash") == ["git commit -F - <<'EOF'", "git push"]


@pytest.mark.parametrize(
    "opener", ["<<EOF", "<<-'EOF'", '<<"EOF"', "<<\\EOF", "<< EOF"]
)
def test_bash_every_heredoc_opener_form(opener):
    command = f"cat {opener}\nbody git stash\nEOF\nnext"
    out = _scrub(command, "bash")
    assert "stash" not in out
    assert segments(command, "bash")[-1] == "next"


def test_bash_two_heredocs_on_one_line():
    command = "cat <<A <<B\nfirst\nA\nsecond\nB\nafter"
    out = _scrub(command, "bash")
    assert "first" not in out and "second" not in out
    assert segments(command, "bash") == ["cat <<A <<B", "after"]


def test_bash_unterminated_heredoc_hides_the_rest():
    """bash reads an unterminated heredoc to end of input."""
    command = "git commit -F - <<'EOF'\npytest | tail with no terminator"
    assert segments(command, "bash") == ["git commit -F - <<'EOF'"]


def test_bash_arithmetic_shift_is_not_a_heredoc():
    command = "echo $((1 << 3)); git stash"
    assert segments(command, "bash") == ["echo $((1 << 3))", "git stash"]


def test_bash_quote_inside_a_comment_opens_nothing():
    command = "git status # don't stash\ngit log"
    assert segments(command, "bash") == ["git status # don't stash", "git log"]


def test_bash_nested_quotes_inside_command_substitution():
    command = 'echo "$(git log --format="%s")"; git stash'
    assert segments(command, "bash")[-1] == "git stash"
    assert "git log" not in _scrub(command, "bash")


def test_bash_escaped_separator_does_not_split():
    assert segments(r"find . -exec rm {} \; ; ls", "bash") == [
        r"find . -exec rm {} \;",
        "ls",
    ]


def test_bash_words_remove_quotes_and_comments():
    assert words('git commit -m "x y" # trailing', "bash") == [
        "git",
        "commit",
        "-m",
        "x y",
    ]


def test_bash_words_fall_back_on_unbalanced_quotes():
    assert words("echo it's", "bash") == ["echo", "it's"]


# --- PowerShell ----------------------------------------------------------------


def test_powershell_here_string_is_blank_including_its_markers():
    command = "git commit -m @'\nfix; git stash\n'@\ngit push"
    out = _scrub(command, "powershell")
    assert "stash" not in out and "@'" not in out
    assert segments(command, "powershell") == [
        "git commit -m @'\nfix; git stash\n'@",
        "git push",
    ]
    assert words(segments(command, "powershell")[0], "powershell") == [
        "git",
        "commit",
        "-m",
        "fix; git stash",
    ]


def test_powershell_double_quoted_here_string_closes_only_at_column_0():
    command = 'Set-Content f.txt -Value @"\n  "@ not yet; git stash\n"@\nls'
    assert segments(command, "powershell")[-1] == "ls"
    assert "stash" not in _scrub(command, "powershell")


def test_powershell_backtick_escape_does_not_split_or_close():
    command = 'Write-Output "a `"; b" ; Write-Output x`;y; git stash'
    assert segments(command, "powershell") == [
        'Write-Output "a `"; b"',
        "Write-Output x`;y",
        "git stash",
    ]
    assert words('Write-Output "a `"; b"', "powershell") == ["Write-Output", 'a "; b']


def test_powershell_backtick_line_continuation_is_one_statement():
    command = "git status `\n  --short; git log"
    assert words(segments(command, "powershell")[0], "powershell") == [
        "git",
        "status",
        "--short",
    ]


def test_powershell_subexpression_is_one_token_with_its_quotes():
    command = 'Write-Output "$(git rev-parse "HEAD")"; $(Get-Date -Format "yyyy MM")'
    first, second = segments(command, "powershell")
    assert words(first, "powershell") == ["Write-Output", '$(git rev-parse "HEAD")']
    assert words(second, "powershell") == ['$(Get-Date -Format "yyyy MM")']


def test_powershell_splatting_and_call_operator():
    assert words("& 'C:\\Program Files\\x.exe' @args -Flag", "powershell") == [
        "&",
        "C:\\Program Files\\x.exe",
        "@args",
        "-Flag",
    ]
    assert words("&git stash", "powershell") == ["&", "git", "stash"]


def test_powershell_semicolon_and_pipeline():
    command = "git status; git log | Select-Object -First 3"
    assert segments(command, "powershell") == [
        "git status",
        "git log | Select-Object -First 3",
    ]
    assert words(segments(command, "powershell")[1], "powershell") == [
        "git",
        "log",
        "|",
        "Select-Object",
        "-First",
        "3",
    ]


def test_powershell_single_quote_doubling():
    assert words("Write-Output 'it''s; fine'", "powershell") == [
        "Write-Output",
        "it's; fine",
    ]
    assert segments("Write-Output 'it''s; fine'; ls", "powershell")[-1] == "ls"


def test_powershell_lone_ampersand_never_splits():
    command = "& git stash; python -m http.server &"
    assert segments(command, "powershell") == [
        "& git stash",
        "python -m http.server &",
    ]


def test_powershell_scriptblock_and_hashtable_are_one_token():
    assert words("Start-Job { python -m http.server }", "powershell") == [
        "Start-Job",
        "{ python -m http.server }",
    ]
    assert words("Invoke-CimMethod -Arguments @{CommandLine='x y'}", "powershell") == [
        "Invoke-CimMethod",
        "-Arguments",
        "@{CommandLine='x y'}",
    ]


def test_powershell_comment_is_dropped_from_words():
    assert words("git status # don't", "powershell") == ["git", "status"]


def test_scrubbed_segments_align_character_for_character():
    command = 'git commit -m "x; y"; git stash'
    for raw, scrubbed in scrubbed_segments(command, "bash"):
        assert len(raw) == len(scrubbed)
