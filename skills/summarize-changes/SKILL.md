---
name: summarize-changes
description: Summarize the current working tree or branch changes, including risks and likely test commands.
---

# Summarize Changes

## Git status

!`git status --short`

## Changed files

!`git diff --name-only HEAD 2>/dev/null || true`

## Diff stat

!`git diff --stat HEAD 2>/dev/null || true`

## Instructions

Summarize:

- what changed
- why it appears to matter
- likely verification commands
- risky files or patterns
- any accidental churn such as lockfiles, generated files, or broad formatting

Keep it concise.
