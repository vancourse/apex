# The session contract

Always loaded; the one place conflicting rules are resolved. Every clause names what enforces it.

**The loop.** Claim → write `.rails/intent.md` and end the turn showing it → the operator's next
message acks or corrects it → commit freely → `rails check` → push → `rails ship` (one PR, Ready,
auto-squash armed) → `rails walk` → the operator says `used`.
→ enforced by: `claim_edit`, `intent_shown`, `prompt_words`, `prepush_marker`, `second_pr`, `turn_end`.

**Push.** Push whenever the check marker exists for HEAD. There is no consent ceremony; the
operator's word is `hold` (lifted by `release`). Never set `RAILS_OPERATOR`, `RAILS_SHADOW_ALL` or
`RAILS_GATES_OFF`: they are the operator's.
→ enforced by: `prepush_hold`, `prepush_marker`, `store_guard`.

**CI is the laptop.** Every lane the diff needs runs locally (`rails check`); CI only verifies the
`rails/<lane>` statuses on the head commit (`rails post`, done by `rails ship`). A lane that cannot
run here says why (`Docker unavailable: not a code failure`) — that is a stop, not a skip.
→ enforced by: the PR `gate` job (`verify-lanes`).

**One PR per line of work.** Slices are commits. Arm auto-squash at open; bind the monitor.
→ enforced by: `second_pr`, `merge_by_effect`, `turn_end`.

**Done is a receipt.** An item closes when its `step:` id passes in a walk receipt on the named
target; fixtures, mocks, dev login and the superuser never close anything. Open items at the end
of a turn need a `stop_reason` (`rails work stop decision_needed|blocked|hold|wip "<text>"`).
→ enforced by: `turn_end`, `rails work done`.

**Household data never leaves the box.** Not in git, CI, issue or PR text, commit messages or
subagent prompts. Use invented values. → enforced by: `leak_dispatch`, `prepush_leak`.

**Statements need receipts.** Done, deployed, reviewed, walked: a receipt id. Existence and absence
claims: `rails whereis <term>` first, and say the scope of a negative.
→ advisory: `rails ship` lists body lines with absence words (`no`, `never`, `missing`, `only`) that
carry no `receipt:` id. Otherwise judgment.

## Judgment

- Read every file in a handoff before planning from any of them; find its precedence statement first.
- A decision for the operator is a brief: the problem in one line, options with costs, the one you
  recommend first.
- Cite the primary artifact (DDL, function body, definition site), never a report of it.
