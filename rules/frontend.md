# Frontend Rules

Note: this file lives at user level (`~/.claude/rules/`) so `paths:` frontmatter is intentionally omitted — it serves as an invocable reference checklist, not an auto-triggered project rule. The `frontend-design` skill covers most of this; this file is a lightweight summary.

- Inspect existing design-system components before creating new UI primitives.
- Reuse existing layout, spacing, typography, and interaction patterns.
- Verify important UI changes in a browser when possible.
- Consider keyboard navigation, focus states, loading states, empty states, and error states.
- Avoid broad visual refactors in feature PRs unless requested.
- Do not hardcode copy, colors, spacing, or breakpoints if the repo has tokens or helpers.
- If using a motion library (Framer Motion / Motion, etc.), gate animations behind `prefers-reduced-motion` and reuse the existing animation pattern — don't introduce a second one alongside it.
