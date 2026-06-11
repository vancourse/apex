#!/usr/bin/env bash
# PreToolUse hook for Edit|Write.
# Inspects the target file path and injects a one-line skill-gate reminder
# when the path matches:
#   (a) an API-surface / payload / handler shape    → invoke apex:api-surface-review
#   (b) apex's own plugin internals                 → read MAINTAINING.md
#       (detected via .claude-plugin/plugin.json with name "apex" in an
#        ancestor directory + path under skills/ commands/ hooks/ rules/)
#   (c) a CI/CD pipeline definition                 → invoke apex:cicd-review
#
# Multiple checks can fire on the same edit (e.g. an api-surface file inside
# apex's own repo) — messages concatenate into one additionalContext line.
#
# Silent for unrelated paths. Always exits 0 — never blocks the edit.

set -u

input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

[ -z "$file" ] && exit 0

# --- Detection: is the edited file inside the apex plugin's own repo? ----
# Walk up to the first .claude-plugin/plugin.json; if its "name" field is
# "apex", we're contributing to the plugin (NOT just using it on another
# project). Bounded walk — stops at first plugin.json found or filesystem
# root, whichever comes first.
in_apex=0
# Ensure file path is absolute before extracting dirname — Claude Code
# usually passes absolute paths, but defensively handle relative (otherwise
# the walk-up loop would never check the repo root via ./.claude-plugin/).
case "$file" in
  /*) ;;  # already absolute
  *)  file="${PWD:-$(pwd)}/${file}" ;;
esac
dir=$(dirname "$file")
while [ -n "$dir" ] && [ "$dir" != "/" ]; do
  if [ -f "$dir/.claude-plugin/plugin.json" ]; then
    # Parse with jq (script already depends on it elsewhere) — robust
    # against any whitespace / formatting in plugin.json. Falls back to
    # in_apex=0 silently if jq errors or the field is missing.
    if jq -e '.name == "apex"' "$dir/.claude-plugin/plugin.json" >/dev/null 2>&1; then
      in_apex=1
    fi
    break  # first plugin.json wins — either we're inside apex or another plugin
  fi
  parent=$(dirname "$dir")
  [ "$parent" = "$dir" ] && break  # idempotent dirname → reached root
  dir="$parent"
done

# --- Build the message(s). Accumulate, emit once. ------------------------
msg=""

# (a) API-surface check — fires regardless of whether we're in apex's own
# repo, because the api-surface-review skill applies to any project.
case "$file" in
  */payloads/*|*/routes/*|*/services/*|*/handlers/*|*/endpoints/*|*/api/*)
    ext="${file##*.}"
    case "$ext" in
      py)
        msg="API-surface path detected (${file##*/}). Before editing, invoke apex:api-surface-review (run all 5 passes against the proposed/current shape) AND apex:python-review. Run BOTH — they are orthogonal."
        ;;
      ts|tsx)
        msg="API-surface path detected (${file##*/}). Before editing, invoke apex:api-surface-review (run all 5 passes against the proposed/current shape) AND apex:typescript-review. Run BOTH — they are orthogonal."
        ;;
      *)
        msg="API-surface path detected (${file##*/}). Before editing, invoke apex:api-surface-review (run all 5 passes against the proposed/current shape)."
        ;;
    esac
    ;;
esac

# (c) CI/CD pipeline check — fires for any project. A workflow file is a
# privileged program that runs other people's input; route authoring/edits
# through the cicd-review gate.
case "$file" in
  */.github/workflows/*.yml|*/.github/workflows/*.yaml|*/.gitlab-ci.yml|*/Jenkinsfile|*/azure-pipelines.yml|*/azure-pipelines.yaml|*/.circleci/config.yml)
    ci_msg="CI/CD pipeline file detected (${file##*/}). Before editing, invoke apex:cicd-review (least-privilege permissions, SHA-pinned actions, injection via untrusted interpolation, OIDC over stored cloud keys, timeouts)."
    if [ -n "$msg" ]; then
      msg="${msg} ${ci_msg}"
    else
      msg="$ci_msg"
    fi
    ;;
esac

# (b) apex-internals check — only fires inside apex's own repo, on paths
# that are part of the plugin's contract (skills, commands, hooks, rules).
if [ "$in_apex" = "1" ]; then
  case "$file" in
    */skills/*|*/commands/*|*/hooks/*|*/rules/*)
      maint_msg="Editing apex plugin internals (${file##*/}). Read MAINTAINING.md for maintainer discipline (pair-pattern verification, slash-count grep) before modifying skills/commands/hooks/rules."
      if [ -n "$msg" ]; then
        msg="${msg} ${maint_msg}"
      else
        msg="$maint_msg"
      fi
      ;;
  esac
fi

# --- Emit (if anything to say). -----------------------------------------
# Use jq -Rs to JSON-encode the message (same pattern as hooks/apex-primer.sh).
# A raw printf with the message interpolated as a string can produce invalid
# JSON if the filename or any interpolated text contains `"`, `\`, or a
# newline — that would silently drop the hook's additionalContext.
if [ -n "$msg" ]; then
  printf '%s' "$msg" | jq -Rs '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:.}}' 2>/dev/null
fi

exit 0
