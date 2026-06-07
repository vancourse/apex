#!/usr/bin/env bash
# PreToolUse hook for Edit|Write.
# Detects edits to security-sensitive paths (auth, credentials, oauth, secrets,
# encryption, signing, SSO, JWT, SAML, OIDC) and injects a review reminder.
#
# Does NOT block — security paths get legitimate edits. Just nudges the model
# to apply review-risk + language-specific security rules before changing them.
#
# Silent for unrelated paths. Always exits 0.

set -u

input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

[ -z "$file" ] && exit 0

case "$file" in
  */auth/*|*/credentials/*|*/oauth/*|*/oidc/*|*/sso/*|*/secrets/*|*/security/*|*/encryption/*|*/signing/*|*/jwt/*|*/saml/*|*/permissions/*|*/authorization/*)
    msg="Security-sensitive path detected (${file##*/}). Before editing, review against rules/review-risk.md (auth/permissions/secrets/data access) and the language-specific security rules (python-review/rules/security.md or typescript-review equivalent). Pay particular attention to: token storage, secret rotation, principal verification, scope/permission checks, redirect-URI validation, and timing-safe comparisons."
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"%s"}}\n' "$msg"
    ;;
esac

exit 0
