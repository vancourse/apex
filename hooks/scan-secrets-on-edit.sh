#!/usr/bin/env bash
# PreToolUse hook for Edit|Write|MultiEdit.
# Scans the content being written for high-signal secret patterns and BLOCKS
# the write on a match. Exit 2 = block + send stderr back to Claude.
#
# Patterns scanned (high-precision; low false-positive):
#   - AWS access key id          AKIA[0-9A-Z]{16}
#   - GitHub personal access tok ghp_[A-Za-z0-9]{36}
#   - GitHub fine-grained token  github_pat_[A-Za-z0-9_]{82}
#   - Stripe live/test secret    sk_(live|test)_[A-Za-z0-9]{24,}
#   - Slack bot token            xoxb-[0-9]+-[0-9]+-[A-Za-z0-9]+
#   - Anthropic API key          sk-ant-[A-Za-z0-9-_]{32,}
#   - OpenAI API key             sk-[A-Za-z0-9]{32,}
#   - Google API key             AIza[0-9A-Za-z\-_]{35}
#   - SSH/RSA private key block  -----BEGIN [A-Z ]+PRIVATE KEY-----
#
# Exempts test fixture markers (anything with FAKE / EXAMPLE / TEST / DUMMY
# in the same line) so synthetic fixtures don't trigger the gate.
#
# Silent on no match. Always exits 0 or 2.

set -u

input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
content=$(echo "$input" | jq -r '.tool_input.content // .tool_input.new_string // empty' 2>/dev/null)

[ -z "$content" ] && exit 0

# Build a single regex with named alternatives.
pattern='(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}|sk_(live|test)_[A-Za-z0-9]{24,}|xoxb-[0-9]+-[0-9]+-[A-Za-z0-9]+|sk-ant-[A-Za-z0-9_-]{32,}|sk-[A-Za-z0-9]{40,}|AIza[0-9A-Za-z_-]{35}|-----BEGIN [A-Z ]+PRIVATE KEY-----)'

# Find lines matching the pattern.
matches=$(echo "$content" | grep -nE "$pattern" 2>/dev/null || true)

[ -z "$matches" ] && exit 0

# Filter out matches that look like deliberate test fixtures
# (line contains FAKE / EXAMPLE / TEST / DUMMY / FIXTURE).
real_matches=$(echo "$matches" | grep -vEi '\b(FAKE|EXAMPLE|TEST|DUMMY|FIXTURE|REPLACE|YOUR_)\b' || true)

[ -z "$real_matches" ] && exit 0

# We have at least one real-looking secret. Block.
echo "BLOCKED: secret-shaped string detected in content being written to ${file:-<unknown>}" >&2
echo "" >&2
echo "Matched line(s):" >&2
echo "$real_matches" | head -5 >&2
echo "" >&2
echo "If this is a real secret: don't commit. Move it to env / secret manager." >&2
echo "If this is a test fixture: prefix / suffix it with FAKE / EXAMPLE / TEST / DUMMY" >&2
echo "to mark it as synthetic, or use an obviously-synthetic value." >&2
echo "If this is a false positive on legitimate code, ask the user to confirm before override." >&2
exit 2
