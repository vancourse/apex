#!/usr/bin/env bash
# PostToolUse hook: auto-format files after Edit/Write.
# Silent on success; never blocks Claude (always exits 0).

set -u

input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

[ -z "$file" ] && exit 0
[ ! -f "$file" ] && exit 0

case "$file" in
  *.py)
    # Use the repo's OWN pinned ruff when it declares one. Formatting is only
    # useful if it agrees with the gate that will judge it: measured 2026-08-13,
    # a repo pinning ruff==0.14.2 in CI had 0.14.14 on PATH, so this hook could
    # reformat a file into a state the repo's own commit gate then rejected —
    # and the fix that gate prints would be undone by the next edit.
    #
    # The pin is READ, never restated here; a second hardcoded version is the
    # same drift bug one layer up. Falls back to PATH ruff when the repo names
    # no pin, which is every repo that does not use this convention.
    py_root=$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null)
    py_pin=""
    if [ -n "$py_root" ] && [ -f "$py_root/ci/pre_pr_check.py" ]; then
      py_pin=$(sed -n 's/^RUFF_VERSION = "\(ruff==[0-9.]*\)".*/\1/p' \
        "$py_root/ci/pre_pr_check.py" 2>/dev/null | head -1)
    fi
    if [ -n "$py_pin" ] && command -v uv >/dev/null 2>&1; then
      uv run --with "$py_pin" ruff format "$file" >/dev/null 2>&1
    elif command -v ruff >/dev/null 2>&1; then
      ruff format "$file" >/dev/null 2>&1
    fi
    ;;
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.json|*.md|*.mdx|*.css|*.scss|*.html|*.yaml|*.yml)
    # Prefer project-local prettier; fall back to global.
    if [ -x "$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null)/node_modules/.bin/prettier" ]; then
      root=$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null)
      "$root/node_modules/.bin/prettier" --write --log-level silent "$file" >/dev/null 2>&1
    elif command -v prettier >/dev/null 2>&1; then
      prettier --write --log-level silent "$file" >/dev/null 2>&1
    fi
    ;;
esac

exit 0
