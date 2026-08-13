#!/usr/bin/env bash
# PostToolUse hook: auto-format files after Edit/Write.
# Silent on success; never blocks Claude (always exits 0).

set -u

input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

[ -z "$file" ] && exit 0
[ ! -f "$file" ] && exit 0

root=$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null)

# Resolve ruff the way the repo's own gates resolve it, and print the argv.
#
# Why this is not `command -v ruff`: the formatter that runs at edit time and
# the formatter the commit gate runs must be the SAME ruff. They were not.
# A floating PATH install formatted a file one way; the gate, running the pin,
# rejected the result — and the remedy the gate printed was undone by the next
# keystroke. Twelve patch versions apart is enough for the two to disagree
# about formatting, and an unformatted file that reaches the default branch
# reddens every open PR, because PR CI builds a merge ref.
#
# Precedence mirrors what a repo has actually declared, strongest first:
#   1. an explicit `RUFF_VERSION = "ruff==X.Y.Z"` pin in ci/pre_pr_check.py —
#      the one place a repo states the version rather than resolving it
#   2. uv.lock / poetry.lock — the same `_runner()` rule apex's own
#      templates/gates/pre_pr_check.py uses to put the repo's environment in
#      front of a tool
#   3. ruff on PATH — no declaration to honour, so nothing to disagree with
#
# A repo whose pin lives behind uv also gets the fix for the second defect:
# the old line did nothing at all, silently, when ruff was not installed.
# `uv run` provisions it.
_ruff_argv() {
  [ -n "$root" ] || { command -v ruff >/dev/null 2>&1 && printf 'ruff\n'; return; }

  if [ -f "$root/ci/pre_pr_check.py" ] && command -v uv >/dev/null 2>&1; then
    # Read the pin rather than restating it — ci/hooks/pre-commit already does
    # this, for this exact reason. Restating it makes a third version to drift.
    pin=$(sed -n 's/^RUFF_VERSION *= *"\(ruff==[0-9][0-9.]*\)".*/\1/p' \
      "$root/ci/pre_pr_check.py" 2>/dev/null | head -1)
    if [ -n "$pin" ]; then
      printf 'uv\nrun\n--with\n%s\nruff\n' "$pin"
      return
    fi
  fi

  if [ -f "$root/uv.lock" ] && command -v uv >/dev/null 2>&1; then
    printf 'uv\nrun\nruff\n'
  elif [ -f "$root/poetry.lock" ] && command -v poetry >/dev/null 2>&1; then
    printf 'poetry\nrun\nruff\n'
  elif command -v ruff >/dev/null 2>&1; then
    printf 'ruff\n'
  fi
}

case "$file" in
  *.py)
    # Read the argv into an array. Newline-delimited rather than word-split so
    # a pin or a path containing spaces cannot split into two arguments.
    ruff_argv=()
    # `|| [ -n "$arg" ]` keeps the last element when the producer forgets its
    # trailing newline — the failure mode there is a SILENTLY TRUNCATED argv
    # (`uv run --with ruff==X format`, which formats nothing and says nothing).
    while IFS= read -r arg || [ -n "$arg" ]; do
      [ -n "$arg" ] && ruff_argv+=("$arg")
    done < <(_ruff_argv)
    if [ "${#ruff_argv[@]}" -gt 0 ]; then
      "${ruff_argv[@]}" format "$file" >/dev/null 2>&1
    fi
    ;;
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.json|*.md|*.mdx|*.css|*.scss|*.html|*.yaml|*.yml)
    # Prefer project-local prettier; fall back to global.
    if [ -n "$root" ] && [ -x "$root/node_modules/.bin/prettier" ]; then
      "$root/node_modules/.bin/prettier" --write --log-level silent "$file" >/dev/null 2>&1
    elif command -v prettier >/dev/null 2>&1; then
      prettier --write --log-level silent "$file" >/dev/null 2>&1
    fi
    ;;
esac

exit 0
