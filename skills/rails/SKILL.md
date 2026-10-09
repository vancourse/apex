---
name: rails
description: The rails loop and its commands - claim, intent, rails check, push, rails ship, walk, used. Use when starting, checking, pushing or shipping any line of work.
---

# The rails loop

One line of work = one claim, one worktree, one branch, one PR, many commits.

1. **Claim** before the first source edit: `rails claim "#123"` · `--milestone "<title>"` · `--adhoc "<line>"`.
   For an issue, `rails work from-issue 123` turns its Done-when lines into the work items this line owes.
   `rails claim --list` shows what sibling worktrees hold; join one rather than cut a second branch.
2. **Intent.** Write `.rails/intent.md` from `rails template intent` (tier `fix` for a
   small fix). End the turn SHOWING it, with its `intent:<hash>` line. The operator's next message
   acks it or corrects it; a correction means rewrite and show again. An agent's push refuses without
   an acked intent (`prepush_intent`).
3. **Walls first.** A new seam's first commit adds its declaration (contract, settings row, auth row,
   concept row, limit name) before code that uses it.
4. **Build and commit.** Tests red first, as the production role, on planted data. Commit freely:
   rails never blocks a commit.
5. **`rails check`** runs every lane the diff selects (`rails/lanes.toml`) and seals a marker for
   HEAD. Long lanes: run it in the background, or one lane at a time with `--lane`. A lane that
   cannot run (Docker down) fails with that reason: fix the environment, never skip it.
6. **Push.** The pre-push hook wants the marker (`--quick` before a PR exists, full after). No
   consent ceremony; the operator's word is `hold`.
7. **Review** a change to anything but prose: run the `rails:reviewer-coop` and `rails:reviewer-adversary`
   agents on the diff (each given only the diff and the intent), save each report, then
   `rails review record --coop <file> --adversary <file>`. Fix every must-fix first; a new commit needs
   a new review, because the receipt is for HEAD's tree.
8. **`rails ship --closes <n>`** opens one Ready PR from the intent (and imports #n's Done-when lines), arms auto-squash, and posts the
   `rails/<lane>` statuses CI verifies. Then bind the monitor and run `rails work monitor-bound`.
   After a later push: `rails check --post`.
9. **Walk** the named target: `rails walk`. An item closes only when its `step:` id passes:
   `rails work done <id>`.
10. **Stop** only with the work done or a recorded reason:
   `rails work stop decision_needed "<problem; options with costs; recommended first>"` | `blocked` | `hold` | `wip`.

Other commands: `rails whereis <term>` before saying anything does not exist; `rails receipt -- <cmd>`
to make a claim checkable; `rails metrics` for the four numbers before/since the cut, CI spend and gate
yield; `rails state`; `rails doctor`; `rails sync` (main checkout to trunk, when safe); `rails history
status` (worktrees on rewritten-away history: never push from one, cherry-pick onto a fresh worktree).
Templates (one set, no other): `rails template` lists intent, spec, adr, milestone, rulebook and the PR
template. A milestone closes with `rails close <n>`, which needs the operator's `used #<n>` and no open
issue. Retiring a hook script: `rails retire-hook <path>` (a deleted one blocks older worktrees).
The operator's own commands, never an agent's (they refuse inside one): `rails release|used|approve`,
`rails snapshot`, `rails enable`. `rails hold` anyone may ask for.

New app: `rails new <app>` gives a walking skeleton with contracts, settings, roots, clock, limits,
concepts and the auth matrix already enforced; its first milestone's step 0 is the operator using it.
