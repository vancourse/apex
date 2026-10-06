# <App> R<n> — <what the operator can now do, in their words>

<!-- DONE = the operator used it. The milestone description is the demo and the
     authority. One issue per step, consolidated where one step is one PR-sized unit. -->

**Step 0 (the operator):** the operator did <real task> on <target>. Receipt: `used #<milestone> <task>`.

**Steps** (on real input; each with a non-zero `expect:` and a `step:` id):

1. `step: s1` — <action> → `expect:` <observation that could come out the other way>
2. `step: s2` — ...

**Walls this release adds** (registry rows, not prose): <contracts / settings / auth rows / concepts / limits>

**Scope valve:** <what gets cut first if it runs long, decided now>

**Closes when:** walk receipt with every step id `pass` + oracle zero-violation receipt (when concepts changed)
+ `used` + `approve` for every rule table touched. `rails close` checks all four.
