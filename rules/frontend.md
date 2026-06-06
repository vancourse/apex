# Frontend Rules

Note: this file lives at user level (`~/.claude/rules/`) so `paths:` frontmatter is intentionally omitted — it serves as an invocable reference checklist, not an auto-triggered project rule. The `frontend-design` skill covers most of this; this file is a lightweight summary.

- Inspect existing design-system components before creating new UI primitives.
- Reuse existing layout, spacing, typography, and interaction patterns.
- Verify important UI changes in a browser when possible.
- **Accessibility (WCAG 2.2 AA — testable acceptance criteria, not "consider"):** every interactive element is **keyboard reachable and operable** (no mouse-only path); a **visible focus indicator** on every focusable control, not obscured by sticky headers/footers (2.2 *Focus Appearance* / *Focus Not Obscured*); **touch/click targets ≥ 24×24 px** (2.2 *Target Size*); **no drag-only interactions** — always offer a single-pointer alternative (2.2 *Dragging Movements*). Treat these as a Definition-of-Done bar on frontend scenarios, not a post-hoc audit.
- Always handle **loading, empty, and error** states explicitly (not just the populated happy path).
- Avoid broad visual refactors in feature PRs unless requested.
- Do not hardcode copy, colors, spacing, or breakpoints if the repo has tokens or helpers.
- If using a motion library (Framer Motion / Motion, etc.), gate animations behind `prefers-reduced-motion` and reuse the existing animation pattern — don't introduce a second one alongside it.
