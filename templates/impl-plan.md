# <Feature> — Implementation plan

**Status:** Draft | **Frozen <date>**
**Upstream:** `design.md` (frozen <date>)

## Layered PR stack

One layer per PR, small enough to review in one sitting. A PR that touches foundation
*and* UI is two PRs.

| # | Layer | What lands | Depends on |
| --- | --- | --- | --- |
| 1 |  |  | — |

## Sequencing

Foundation → service → API → UI. Name anything that must land in a different order and
why the dependency runs backwards.

## Test plan per layer

Each PRD scenario maps to at least one integration test. Fill both columns — a scenario
with no test is a scenario that will not be verified.

| PRD scenario | Layer | Test | Tier |
| --- | --- | --- | --- |

New package or module in this plan? Enumerate every place it must be **registered**
before it is reachable — workspace/member lists, dependency groups, type-checker
includes, capability indexes, and a copy step in each deploy image. This list is
always longer than it looks, and a package registered in most of them is unreachable
in exactly the environment nobody tested.

## Rollout

Feature flag | direct deploy | migration-first | compatibility window. Say which, and
what the un-gating condition is if it ships behind a flag.

## Reversibility

Per layer: how it is rolled back, and whether the rollback is clean or leaves state
behind. A migration that cannot be reversed must say so here, loudly.

| Layer | Rollback | Clean? |
| --- | --- | --- |

## Wiring

Who imports or invokes this once each layer lands. A layer whose answer is "nothing yet"
is fine — say so, and say what changes it. Silence here is how the platform accumulated
capabilities that pass every gate and run in no process.

## Freeze record

| Date | Change | Why |
| --- | --- | --- |
