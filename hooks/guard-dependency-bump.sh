#!/usr/bin/env bash
# PreToolUse hook for Edit|Write|MultiEdit.
# Detects edits to dependency manifests / lockfiles and injects a review-risk
# reminder. Dependency bumps are a high-risk-low-attention class of change.
#
# Does NOT block — bumps happen routinely. Just nudges the model to apply
# review-risk discipline before changing them.
#
# Silent for unrelated paths. Always exits 0.

set -u

input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

[ -z "$file" ] && exit 0

basename="${file##*/}"
case "$basename" in
  package.json|package-lock.json|pnpm-lock.yaml|yarn.lock|npm-shrinkwrap.json|\
  uv.lock|Pipfile|Pipfile.lock|poetry.lock|pyproject.toml|requirements.txt|requirements-*.txt|\
  Cargo.toml|Cargo.lock|go.mod|go.sum|Gemfile|Gemfile.lock|composer.json|composer.lock)
    msg="Dependency / lockfile change detected (${basename}). Review against rules/review-risk.md (large dependency or lockfile changes). Verify: (1) only the intended deps changed — no transitive surprises, (2) lockfile matches the manifest after the change, (3) full build + test + type-check still pass, (4) no new high-severity audit warnings, (5) for major version bumps, check the upstream changelog for breaking changes."
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"%s"}}\n' "$msg"
    ;;
esac

exit 0
