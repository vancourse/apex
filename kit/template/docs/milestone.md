# __App__ R1 -- milestone

DONE = the operator used it.

## Steps

0. **step: s0** -- the operator did `<task>` on `<target>`; receipt: `used`.
1. **step: a1** -- a member exports the month's entries as CSV from the summary
   screen; `expect:` the walk finds an "Export CSV" control and the file holds
   one row per planted entry of the month. (Fails today, on purpose.)

## Walls

- Planted values only in this repo; the real store is reached by `rails oracle`.
- Every acceptance line has a `step:` id; an item closes only on a passing receipt.

## Scope valve

What this release drops first if it runs long, written before it does.
