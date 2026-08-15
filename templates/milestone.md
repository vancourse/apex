# <Lane> R<n> — <outcome a person can watch>

This is the shape of a milestone's **description** — the text you paste into the
milestone body on the forge. It is not a file in the repo. The milestone is the
release; the description below is what makes "done" a thing somebody can observe
rather than a thing somebody feels.

The title is an outcome, not a theme. "Ingest R2 — a CSV lands and the dashboard
shows its rows" is watchable; "Ingest improvements" is not, and a title nobody can
watch produces a milestone nobody can close.

---

Dossier: `docs/<slug>/design.md`

**DONE = THIS DEMO, run by the operator**

1. <observable step> — `<the real command>` → <what the operator sees>
2. <observable step> — <input named: the actual file, tenant, account, endpoint>
3. <observable step> — <the assertion a bystander could check>

**Input:** <the real input this demo runs on>

**Scope valve:** a further issue found while building this is **R<n+1> scope**
unless it makes one of the numbered steps above false.

---

## The rules this shape encodes

**One step per issue, 1:1.** Every numbered step is exactly one issue, and every
issue under this milestone is exactly one step. That correspondence is what lets
the completion gate mean anything: when the last issue closes, the demo is
runnable, so the milestone is finished and the only thing left is to close it.

**Steps are observations, not activities.** "Wire the parser into the loader" is
an activity — it is true the moment somebody says it is. "`ingest sample.csv`
exits 0 and `SELECT count(*)` returns 1,204" is an observation, and it can come
out the other way. Write the second kind. The same test applies to each issue's
`Done when`, which is where it is enforced.

**Name the real input.** A demo on a fixture demonstrates the fixture. If the
release is about handling the customer's export, the demo runs on the customer's
export — or on a named, checked-in sample of it, and the description says which,
so nobody reads a green fixture as a green customer.

**The demo is runnable from the milestone's first PR.** That PR is the walking
skeleton: every step present, wired end to end, failing honestly. An operator who
can run it on day one finds out on day one that it is the wrong thing. See
`apex:release-loop` step 5 for what "walls before rooms" means for that PR.

**The scope valve is written in advance, not negotiated later.** Written before
the work starts, it is a rule; written when the tempting issue appears, it is a
decision made under pressure by the person who wants to say yes. The valve's one
exception — "unless it makes a numbered step false" — is deliberately the only
way scope grows inside a release.

**A defect found during the demo is R<n+1> scope** under the same valve. If it
breaks a numbered step, it is this release and the milestone stays open; if it
does not, it is the next one and this milestone still closes. Route it through
`apex:investigate-bug` and the defect form either way.

## Closing

The operator runs the demo. All numbered steps true → close the milestone. Not a
review, not a sign-off — the steps were written to be checkable precisely so that
closing needs no judgement.

`templates/gates/milestone_completion_gate.py` is the backstop, not the decision:
on a scheduled lane it fails when a milestone whose issues are all closed has sat
open past its grace period. It catches the release everybody finished and nobody
closed — measured at 11 of 47 on a real repo's first 33 days. It cannot tell you
a release is finished when the work was never filed as issues, which is why the
numbered demo above is the definition and the gate is only the reminder.
