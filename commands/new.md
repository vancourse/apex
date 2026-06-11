---
description: "[USER] Create a new project from scratch (or adopt apex in an existing one) — intake → architecture-design → official-generator scaffold → docs/ + CLAUDE.md + CI baseline wiring → first walking-skeleton PRD"
---

Invoke the `project-bootstrap` skill from the apex plugin for this task. Read its SKILL.md and follow it.

Mode-detect first (existing source + git history → ADOPT, confirm with the user; otherwise GREENFIELD), honor the YAGNI guard for throwaway tools, and route P1 to `apex:architecture-design` and P4's CI baseline through `apex:cicd-review` rather than duplicating either.
