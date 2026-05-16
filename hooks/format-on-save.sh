#!/usr/bin/env bash
# PostToolUse hook: auto-format files after Edit/Write/MultiEdit.
# Silent on success; never blocks Claude (always exits 0).

set -u

input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

[ -z "$file" ] && exit 0
[ ! -f "$file" ] && exit 0

case "$file" in
  *.py)
    command -v ruff >/dev/null 2>&1 && ruff format "$file" >/dev/null 2>&1
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
