---
name: ui-design-review
description: Design-and-build gate for user-facing UI — 5-pass discipline that turns rules/frontend.md from a checklist into an enforced loop: design-system conformance (reuse the existing component/token before inventing one — the first-affordance check applied to UI), the five view states designed up front (loading / empty / error / partial / ideal), interaction + WCAG 2.2 AA as Definition-of-Done (keyboard-operable, visible focus, ≥24×24 targets, no drag-only, prefers-reduced-motion), the LOOK-AT-IT loop (render → screenshot → critique against the design → iterate, ≤3 rounds then human — never claim visual work done without having seen pixels; extends apex:verification-before-completion to the visual layer), and promotion of stabilized key screens to test-strategy Layer 7 visual regression. Distinct from the frontend-design companion plugin (aesthetic generation; this gate audits), rules/frontend.md (the checklist this enforces), and typescript-review (code idiom, not visual correctness). Keywords: UI, frontend, design system, component, screenshot, visual, accessibility, WCAG, a11y, empty state, loading state, responsive, design review, looks wrong, pixel.
---

# UI Design Review (the LOOK-AT-IT gate)

UI work has a failure mode no other apex gate catches: code that passes every test and is **visually wrong** — broken at the breakpoint nobody rendered, an empty state nobody designed, a focus ring nobody could see. The root cause is always the same: nobody *looked*. This gate makes looking mandatory. Fires at design time for user-facing features and during implementation of UI diffs.

## Pass 1 — Design-system conformance (first-affordance, applied to UI)

- Inventory first: which existing components/tokens/patterns already solve this? A new component requires the same justification as a new abstraction in `apex-flow` §1b — name the considered-and-rejected existing component.
- No hardcoded colors, spacing, type sizes, or copy — tokens and the copy mechanism the project already uses (`rules/frontend.md` rules, now audited rather than recalled).
- New variants extend the existing component (a `variant` prop) rather than forking it (`ButtonNew` is the pure-addition smell wearing CSS).
- Motion: reuse the established animation pattern; everything gated behind `prefers-reduced-motion`.

**Adversarial counter:** diff the proposed UI against the app's three nearest screens. Every divergence (different button height, new shade of gray, novel empty-state layout) is either justified in writing or a defect.

## Pass 2 — The five states (designed, not discovered)

Every view in the feature gets all five states **at design time**:

1. **Loading** — skeleton/spinner choice, layout shift on resolve.
2. **Empty** — first-run with zero data: a designed moment with a CTA, not a blank `<div>`.
3. **Error** — what the user reads (not the exception), and the recovery affordance.
4. **Partial** — 1 item, 10k items, the 300-character name that breaks the layout, offline/stale data.
5. **Ideal** — the only one mockups ever show.

**Adversarial counter:** for each view, ask "what renders when the API returns `[]`? when it 500s? when it hangs 10 seconds?" An answer of "whatever the framework does" fails the pass.

## Pass 3 — Interaction + accessibility (WCAG 2.2 AA as DoD)

The `rules/frontend.md` bar, audited per-flow: the entire flow is **keyboard-operable** (walk it with Tab/Enter/Esc — modals trap and restore focus); focus is **visible and un-obscured** on every interactive element; targets ≥ **24×24px**; **no drag-only** interactions; inputs carry labels (placeholder ≠ label) and errors are announced (associated, not color-only); images carry alt text or explicit decorative marking; contrast meets AA.

**Adversarial counter:** run the primary flow once with the mouse unplugged and once squinting (can you still tell what's primary, focused, and wrong?). Each failure is a named finding, not a "polish later."

## Pass 4 — The LOOK-AT-IT loop (visual verification)

The visual extension of `apex:verification-before-completion`: **never claim UI work done without having seen rendered pixels.**

1. Render the change (dev server, Storybook, or the real app).
2. **Screenshot** — agent-driven browser (Playwright MCP or equivalent) at desktop + smallest supported viewport; capture key states from Pass 2, not just ideal.
3. **Critique against the design** — layout, hierarchy, spacing rhythm, design-system fidelity. The squint test: does the visual weight match the intended importance?
4. Iterate. **Budget: ≤3 screenshot→fix rounds**, then stop and show the human — visual convergence past 3 rounds means the design itself is ambiguous (a Pass-1/2 defect, not a CSS problem).

"Tests pass" claims nothing about pixels. The artifact of this pass is the screenshots themselves — attach them to the PR (`pr-review-primer` gets a *what it looks like* section for UI diffs).

## Pass 5 — Visual-regression promotion

Stabilized key screens (the ones a regression would embarrass) get promoted to `apex:test-strategy` **Layer 7 (Visual-E2E)** with a named owner spec — consciously and sparingly: visual snapshots of churning screens are flake generators. Note what was deliberately NOT promoted and why. E2E-tagged PRD scenarios with a UI surface keep their Layer 6 spine-Playwright owner regardless (that's `impl-plan-review`'s rule; this pass only adds the visual layer).

## YAGNI guard

Internal admin tooling and dev-only surfaces get Passes 2 and 4 only (states + look-at-it) — conformance and visual-regression ceremony are for surfaces users live in. A backend-only diff with no rendered surface skips this gate entirely.
