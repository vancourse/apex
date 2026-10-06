---
name: release
description: Start or close a release (a milestone whose done is the operator using it). Use for new apps, versions and features; fixes use the fix skill.
---

# The release loop

1. **Milestone first** from the plugin's `templates/milestone.md`. Step 0 is "the operator did
   <task> on <target>". Every step has a `step:` id and an `expect:` that could come out the other way.
2. **Issues**: one per step, consolidated where one step is one PR-sized unit. Each has a falsifiable
   "Done when".
3. **Spec only where the intent cannot carry it** (a seam, a new concept, a model in the loop, a
   trust boundary): `templates/spec.md`, one authoring pass, one adversarial pass (`design-review`), build.
4. **Contract first.** The walls the release adds (contracts, settings, auth rows, concepts, limits)
   land in its FIRST PR, with tests that fail on a planted defect.
5. **The demo runs from PR 1**, failing honestly, so wrongness is visible on day one.
6. **Build each line of work through the `rails` loop.** WIP is one app: a second release milestone
   waits for the first's `used`.
7. **Close** only with: every step id passing in a walk receipt on the named target, a
   zero-violation oracle receipt when concepts changed, the operator's `used`, and `approve` for
   every rule table touched.
8. **Retro**: run the `retro` skill.
