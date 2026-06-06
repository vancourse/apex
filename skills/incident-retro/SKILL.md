---
name: incident-retro
description: Post-release learning loop — take a RESOLVED production incident and run a blameless retro whose payload is mapping the incident to the apex gate that SHOULD have caught it, then writing the durable lesson to domain-knowledge via memory-note and proposing a one-line preventative gate amendment. The adversarial counterpart to the memory loop: apex learns from reviews/designs but this is how it learns from production failures. NOT incident response — no paging, sev levels, or live timelines; the learning half only. User-invoked, zero ambient cost. Pairs with apex:memory-note (persists the lesson), superpowers:systematic-debugging (finds the cause this reacts to), and FLOW.md (the gate catalog it maps against). Keywords: incident, postmortem, retro, blameless, post-release, learned the hard way, production bug, which gate missed it, corrective action, prevent recurrence.
---

# Incident Retro (Post-Release Learning Loop)

apex's memory loop learns from **reviews and designs** — lessons surfaced while
building. It never learns from **production incidents**. When something apex's
gates *should* have caught reaches prod and breaks, this skill closes the loop:
it runs a blameless retro, identifies **which apex gate missed it**, writes the
durable lesson, and proposes the gate amendment that would catch the class next
time.

It is the **learning half** of a postmortem only. It is explicitly **not** an
incident-response tool — no paging, no severity classification, no live
timelines. It runs **after** an incident is resolved, is **user-invoked** (no
hooks, zero ambient cost), and **never self-mutates apex** (it *proposes*; a human
applies the change through apex's normal PR gates).

## When to invoke

- After a production incident (or a **near-miss** caught in staging — a free
  lesson) has been **resolved** and its technical cause is known.
- "What gate should have caught this?" / "post-mortem this" / "add the lesson."

Do **not** invoke:
- **Mid-incident** → redirect: "resolve it first; this is the learning pass."
- **Before the cause is known** → run `superpowers:systematic-debugging` first;
  you can't map a miss without a cause. This skill starts *after* the cause.

## The four moves

### 1. Blameless reframe

Restate the incident as **contributing conditions and gate gaps**, never people
or "should have been more careful." If a draft says "the engineer forgot X,"
rewrite to the system condition ("no gate required a check for X on this path").
Blameless-but-vague ("the team should be careful") also fails — it must be
specific enough to act on.

### 2. Gate-miss mapping

Load the gate catalog from **`FLOW.md`** (the skill × phase matrix — the
authoritative, current list; don't carry a private copy that drifts). Name the
**specific gate(s)** that should have caught this:

- a `design-feature` Pass 5 failure mode? a `threat-model` STRIDE category? an
  `impl-plan-review` Pass 5 reversibility check? a `test-coverage-audit` failure-
  path test? a missing observability signal?
- An incident may map to **two** gates — name all of them, not just the first.
- If **no existing gate** covers this class, say so explicitly — that "no covering
  gate" finding is itself the highest-value output (a candidate new gate).

### 3. Durable lesson → `domain-knowledge`

Write **one** durable, non-obvious fact via `apex:memory-note` to
`~/.claude/domain-knowledge/<project>.md` so the next design/session starts
smarter. **Dedup first**: if a near-identical lesson already exists, update /
annotate it rather than appending a duplicate. Capture the **lesson/class**, not
raw incident data — **do not paste secrets, tokens, or PII** into the durable
lesson.

A retro that ends without a written lesson + a named gate-miss (or an explicit
"no covering gate") is **incomplete**.

### 4. Corrective actions (specific + owned)

Produce ≥1 of each, each specific and with an owner:

- **Mitigative** — stop the immediate bleeding.
- **Preventative** — the gate change that catches the *class*. This is a
  **one-line proposal** ("add a query-plan check to `impl-plan-review` Pass 4 for
  new hot-path reads"). If pursued, it feeds a normal `/apex:prd` or skill-edit
  PR — **keep it one line; do not inline a mini-spec here** (that's the
  scope-explosion wall — `incident-retro` is not a feature-authoring tool).

Vague actions ("improve test coverage") fail — push to the specific, owned form.
Every escape needs a *preventative* companion, not only a mitigation.

## Output

A short markdown retro (contributing conditions · gate-miss · lesson · actions) +
the `domain-knowledge` append. Nothing else — no store, no metrics, no timeline.

## Invariants (do not break)

- **Learning half only** — no paging / sev / response tooling (that's a different
  product apex deliberately doesn't own).
- **apex does not self-mutate** — preventative actions are *proposals* a human
  carries through the normal gates.
- **Zero ambient cost** — user-invoked; no hooks, no background.
- **No secrets/PII** in the durable lesson.

## Relationship to other skills

- **`apex:memory-note`** — this is the *structured producer* of an incident-class
  lesson; it *calls* `memory-note` to persist. It does **not** create a second
  lesson store.
- **`superpowers:systematic-debugging`** — finds the technical cause; this starts
  after, asking "which gate should have caught it?"
- **`verification-before-completion`** — proves a change works *pre-merge*; this
  learns from what broke *post-release*. Opposite ends of the same loop.
- The loop closes back on apex: a "no covering gate" finding feeds `/apex:prd`,
  and the resulting amendment is checked by `apex:cross-artifact-consistency`.
