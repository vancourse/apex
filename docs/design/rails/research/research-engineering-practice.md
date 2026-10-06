# Established engineering practice, mapped to our defect classes

Research brief for the rails designers, 2026-10-05, written against `evidence_report.md`,
the coverage matrix, PR-01..PR-20 and the transcript analysis.

**How to read an entry.** What; canonical source; evidence strength (**measured** =
quantitative study or production data; **adopted** = widely used, maintainer-documented, no
controlled study; **opinion** = a respected practitioner's argument); class addressed; cost
for a solo developer with concurrent agent sessions (low / med / high, per-PR cost named);
failure mode. Shares are of the 1,007-defect pool. Every URL was fetched or returned by a
search this session; where a figure could not be re-read from the primary, the entry says so.

---

## 0. Three findings that frame the design

**AI adoption lowers delivery stability unless batch size and testing hold.** DORA 2024: a
25% increase in AI adoption goes with a 1.5% decrease in delivery throughput and a 7.2%
decrease in delivery stability, while raising self-reported documentation quality 7.5%.
DORA's reading: "improving the development process does not automatically improve software
delivery — at least not without ... small batch sizes and robust testing mechanisms"
([Google Cloud, 2024 DORA report](https://cloud.google.com/blog/products/devops-sre/announcing-the-2024-dora-report);
[dora.dev](https://dora.dev/research/2024/dora-report/)). That is our 58% rework share seen on
a population. *Measured.*

**Self-reports of progress are not receipts.** METR's randomized trial (16 experienced
maintainers, 246 real issues, early 2025): developers took 19% longer with AI tools, had
forecast a 24% speedup, and afterwards still believed they had been 20% faster
([METR, 2025](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)).
METR calls it a snapshot; the perception gap is the durable lesson, the shape of our "77% of
self-corrections were wrong statements". *Measured, small n.*

**Reminders do not prevent errors; forcing functions do.** Norman separates forcing functions
— interlocks (force the right order), lock-ins (prevent stopping early), lockouts (prevent an
action) — from signage ([Norman, Design of Everyday Things](https://jnd.org/preface-design-of-everyday-things-revised-edition/)).
Our deny hooks worked; prose was broken four turns after being quoted; nudges were followed
13% of the time. Every rule in the design is an interlock, lock-in or lockout, or it is
signage and is cut. *Opinion, long applied record.*

---

## 1. Seams: wiring 15.7%, deploy/config 10.5%, contract drift 8.9%

### 1.1 Schema-first: one declaration generates the other sides

**What.** The OpenAPI document, the SQL, or the message schema is the single authored
artifact; clients and models are generated from it, so drift fails compilation rather than a
screen. [openapi-typescript](https://openapi-ts.dev/introduction) turns OpenAPI 3.x into
types with no runtime cost; FastAPI documents SDK generation as the sanctioned path
([FastAPI, Generating SDKs](https://fastapi.tiangolo.com/advanced/generate-clients/));
[sqlc](https://docs.sqlc.dev/) compiles SQL into type-checked code; [`buf breaking`](https://buf.build/docs/breaking/)
diffs a schema against a baseline and fails CI on wire-incompatible change.

**Evidence.** *Adopted*; the mechanism is deterministic.

**Addresses.** contract_drift (codegen/static types: 27 of 71); 23 routes bypassing
`response_model` (#2326); vocabularies copied per package; PR-15.

**Cost.** Low: a generation step and `git diff --exit-code` on the output; seconds; the
failure names the field.

**Failure mode.** Generation run by hand drifts; CI must regenerate and fail on diff. Codegen
pins shape, not meaning: a generated enum still lets the UI render a state the engine never
writes (1f6541bc0c), which needs PR-15's emit/consume test.

### 1.2 Consumer-driven contract testing (Pact)

**What.** The consumer records the interactions it needs; the provider replays them; a
broker stores results; `can-i-deploy` refuses a deploy whose contracts are unverified
against what is live ([Pact, can-i-deploy](https://docs.pact.io/pact_broker/can_i_deploy)).

**Evidence.** *Adopted.* Pact's scoping page says it fits when you "control the development
of both the consumer and the provider", and not for public APIs, performance, "functional
testing of the provider — that is what the provider's own tests should do", or "as a general
purpose mocking or stubbing tool for browser driven tests"
([Pact, what is Pact good for](https://docs.pact.io/getting_started/what_is_pact_good_for)).

**Addresses.** contract_drift (contract test: 26 of 71).

**Cost.** Med–high: a broker is infrastructure and every consumer change publishes a pact.
Its value over 1.1 is independent deployability of separately owned services, which one
operator with one deploy train does not have.

**Failure mode.** Pacts that mirror provider unit tests become a second copy of the
contract. **Judgment:** keep the shape (jarvis's contract gate already is it), skip the
broker; the browser extension against the fleet is the only seam with its own release cadence.

### 1.3 Composition root, fail fast, walking skeleton, boot smoke

**What.** Compose the object graph in one place, as close to the entry point as possible
([Seemann, Composition Root](https://blog.ploeh.dk/2011/07/28/CompositionRoot/)); a root is
application-specific and not reusable ([Seemann, Composition Root Reuse](https://blog.ploeh.dk/2015/01/06/composition-root-reuse/)).
A program that cannot satisfy a startup precondition stops immediately and visibly
([Shore, "Fail Fast", IEEE Software 2004](https://www.martinfowler.com/ieeeSoftware/failFast.pdf)).
Begin with a walking skeleton, "a tiny implementation of the system that performs a small
end-to-end function" ([97 Things, after Cockburn](https://www.oreilly.com/library/view/97-things-every/9780596800611/ch60.html)).

**Evidence.** *Opinion / adopted*, plus our own measurement: booting the real root was the
cheapest catch for 130 defects (12.9%); `fleet-smoke` found three and gated nothing.

**Addresses.** wiring_integration (42 of 88), data_persistence, second-root parity (#2270,
#2357, eeae3969c7), `Null` defaults in production (#2315); PR-01, PR-02, PR-10.

**Cost.** Med to build once; then a required 2–5 minute job on app / toolbox / runtime /
deploy paths. A red boot smoke names the route, so it costs no diagnosis.

**Failure mode.** A boot check that guards handlers but not schedules (#1064), or that runs
on a schedule into silence (37 red runs). Fail-fast means one bad secret takes the fleet
down, so the design names which settings are fatal and which degrade to the designed "not
composed here" state (design-gui.md §3a, which was right).

### 1.4 Real dependencies in tests (Testcontainers)

**What.** A throwaway real Postgres (or broker, or object store) per test session, "the
same services you use in production without mocks or in-memory services"
([Testcontainers](https://testcontainers.com/); [GitHub](https://github.com/testcontainers/)).

**Evidence.** *Adopted.*

**Addresses.** Mock-passes-real-fails in both repos (e2a9040a26, 6bd453e533, aa35c6f224);
superuser rigs, once the container is provisioned with the production role (PR-13).

**Cost.** Low–med: Docker already runs here; 5–20 s per session. The real cost is making
"created as owner, connected as NOSUPERUSER NOBYPASSRLS" the **default** fixture.

**Failure mode.** A fresh container never exercises migrate-from-previous (0272d9dc40) or
boot-twice idempotency (b2d5292078); the boot smoke carries those steps.

### 1.5 Config in the environment, declared once, validated at startup

**What.** Twelve-factor keeps config in the environment, separated from code
([12factor.net/config](https://12factor.net/config)). Typed settings validate it at process
start, so a missing or malformed variable is a startup `ValidationError`; `extra="forbid"`
makes a misspelt variable an error ([pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)).

**Evidence.** *Adopted.* The "declared once" half (renderer, compose, validator and settings
checked against one declaration) is PR-03, not a published practice.

**Addresses.** deploy_env_config (preflight: 50 of 90): nine env fixes in seven days,
`--sync` losing 4 then 12 keys, the RP id never forwarded, `${VAR:-}` forwarding absence as
empty.

**Cost.** Low: a sub-second test asserting the three sets are equal; the failure names the
variable and the file lacking it.

**Failure mode.** Defaults everywhere validate nothing: production-required fields must be
required. A hand-launched server's inherited environment is still unknown (#2062), so the
preflight prints effective settings beside the result.

### 1.6 For the open question: monolith first, the wrong abstraction

**What.** Fowler: "almost all the successful microservice stories have started with a
monolith", and greenfield microservice systems mostly "ended up in serious trouble"; the
premium is paid before the system needs it ([MonolithFirst](https://martinfowler.com/bliki/MonolithFirst.html);
[MicroservicePremium](https://martinfowler.com/bliki/MicroservicePremium.html)). Metz:
"duplication is far cheaper than the wrong abstraction"; an abstraction extracted before the
second caller "sprouts teeth" ([The Wrong Abstraction](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction)).

**Evidence.** *Opinion* from large observed samples; consistent with our seam share (42% of
jarvis product fixes, 45% of gaps) and 1,175 zero-caller lines in one toolbox (#2348).

**Addresses.** The brief's open question: the literature supports extraction when the second
consumer exists and is wired (PR-10 as an extraction rule), not 38 toolboxes as a start.

**Cost.** Negative: fewer packages, seams and parity tests.

**Failure mode.** Under-extraction duplicates a domain rule (income x4); the counterweight
is one owner per **rule** (1.7, 3.4), not one package per capability.

### 1.7 Architecture as executable fitness functions

**What.** "An objective integrity assessment of some architectural characteristic", run
continuously, so architecture is governed by tests rather than documents
([Ford, Parsons, Kua](https://nealford.com/downloads/Evolutionary_Architectures_by_Neal_Ford.pdf)).
[import-linter](https://import-linter.readthedocs.io/en/stable/) enforces `forbidden`,
`protected`, `layers`, `independence` and acyclic-sibling contracts from one file.

**Evidence.** *Adopted*; used on very large Python monoliths.

**Addresses.** PR-07 (a registered concept computed only in its owner); the never-call-fetch
rule that lived in prose (#2225); app/toolbox layering.

**Cost.** Low: a contract file and a sub-second check naming the importing module.

**Failure mode.** Import rules cannot see arithmetic on period strings or a private enum
copy; the concept gate needs an AST or grep rule beside it, with a case from outside its list.

---

## 2. The harness itself 10.4% and test defects 5.0%

### 2.1 Flaky-test science and the trust threshold

**What.** Google: "If each test has even a 0.1% of failing when it should not, and you run
10,000 tests per day, you will be investigating 10 flakes per day"; "as you approach 1%
flakiness, the tests begin to lose value", after which "engineers will stop reacting to test
failures, eliminating any value the test suite provided"
([Software Engineering at Google, ch. 11](https://abseil.io/resources/swe-book/html/ch11.html)).
Google's practices — rerun policy, flaky tag and dashboard, test owners — are in
[Micco, 2016](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html).
Luo et al. categorised 201 flaky-test fixes in 51 projects; the largest causes were async
waits, concurrency and test-order dependency ([FSE 2014](https://experts.illinois.edu/en/publications/an-empirical-analysis-of-flaky-tests);
percentages not re-read here). Microsoft root-caused flakes by instrumenting runtime calls
([Lam et al., ISSTA 2019](https://www.microsoft.com/en-us/research/wp-content/uploads/2019/11/LamETAL19RootFinder.pdf));
Meta scores flakiness as a probability — "not whether a particular test is flaky, but how
flaky it is" ([Machalica et al., 2020](https://engineering.fb.com/2020/12/10/developer-tools/probabilistic-flakiness/)).
Fowler's remedy is bounded quarantine — "only allow 8 tests in quarantine" or "no longer than
a week" — and he names time ("direct calls to system clocks") among five causes
([Eradicating Non-Determinism in Tests](https://martinfowler.com/articles/nonDeterminism.html)).

**Evidence.** *Measured* (production data at three companies). We are far past the
threshold: 84.5% of scheduled runs red, 44% of job failures caused by the checks.

**Addresses.** harness_self; red carrying no information; 101 identical reds from an expired
dated corpus (a Fowler "time" cause).

**Cost.** Low per PR: a quarantine marker with owner and date, and a test that fails when the
list exceeds N or an entry is older than D.

**Failure mode.** Unbounded quarantine is a graveyard; rerun without a dashboard hides the
rate. For one developer the owner is always the same person, so the date is the binding term.

### 2.2 Mutation testing, surfaced where it is read

**What.** Insert small faults; check the tests catch them. Google mutates only changed,
covered, non-"arid" lines and surfaces survivors as review comments: "testing 1.1 million
mutants and surfacing 150,000 actionable findings during code review ... the reported
usefulness of the surfaced results improved from 20% to 80%"
([Petrović & Ivanković, ICSE-SEIP 2018](https://research.google.com/pubs/archive/46584.pdf)).
Tools: [mutmut](https://mutmut.readthedocs.io/); [StrykerJS `--incremental`](https://stryker-mutator.io/docs/stryker-js/incremental/)
re-tests only changed code, and `thresholds.break` fails the build
([configuration](https://stryker-mutator.io/docs/stryker-js/configuration/)).

**Evidence.** *Measured* at Google; tool docs otherwise.

**Addresses.** test_defect (mutation-checking the test: 41 of 49): tautological guards,
self-supplied preconditions, fabricated fixtures. It also tests the **gates**: a planted
defect is a hand-written mutant, so PR-12 is mutation testing applied to CI.

**Cost.** Med: whole-tree runs take hours; incremental on the diff's files is 1–5 minutes.
Attention: a list of survivors, one line each.

**Failure mode.** A survivor is not evidence of a weak test until the mutant changes
behaviour (`new Set(undefined)`); equivalent mutants burn attention. Google's answer was
arid-node suppression plus a one-click "not useful"; ours is a dated per-file allowlist.

### 2.3 Coverage is not effectiveness; change detectors are not tests

**What.** Over 31,000 generated suites on five Java systems, once suite size is controlled
the coverage–effectiveness correlation is "low to moderate", so "it is not generally safe to
assume that effectiveness is correlated with coverage" ([Inozemtseva & Holmes, ICSE 2014](https://dl.acm.org/doi/10.1145/2568225.2568271)).
A test that "fails in response to any change to the production code, even if the behaviour
... remains unchanged" adds no clarity and blocks refactoring ([Google Testing Blog, 2015](https://testing.googleblog.com/2015/01/testing-on-toilet-change-detector-tests.html)).

**Evidence.** *Measured* (coverage); *opinion* (change detectors).

**Addresses.** Keeps a coverage threshold out of the design (`modules-are-consumed`
discharged by any import, #2348, is the same false proxy). Sherpa gate B (216 failures, 0
defects) and a walkthrough asserting text copied from the POST response were change detectors.

**Cost.** None; a review question: would this fail if behaviour were wrong and pass if only
the implementation moved?

**Failure mode.** Over-reading: coverage still finds never-executed code, which is how Google
scopes mutants; golden masters (3.1) are deliberate change detectors on person-approved
outputs, the one right place for that instrument.

### 2.4 DORA metrics as the harness's scoreboard

**What.** Deployment frequency, lead time, change failure rate, time to restore, plus (2024)
**deployment rework rate**, the share of deployments that are unplanned fixes
([dora.dev, metrics history](https://dora.dev/insights/dora-metrics-history/)).

**Evidence.** *Measured* (ten years of surveys); descriptive, not causal.

**Addresses.** Layer 7: a harness that must cite the defects it caught needs a denominator;
our rework share is the rework rate.

**Cost.** Low: derived weekly from git and the PR list; never hand-kept.

**Failure mode.** Relabelling fixes as features. The guard is the classifier behind this
synthesis, scheduled, surfaced by the SessionStart hook, where unread signals became read.

### 2.5 "Report-only until green, then required" — its failure mode

**What.** Run a new check unrequired; require it once it passes. Our counter-case:
`purser-e2e` red 101 of 101 and `sherpa-geometry` 102 of 102 while unrequired, because nobody
watches an unrequired job. Fowler's quarantine bound (2.1) and Google's "test certified"
ladder — five levels of "concrete actions", ending at "all nondeterminism had been removed"
([SWE at Google ch. 11](https://abseil.io/resources/swe-book/html/ch11.html)) — work because
they are dated and bounded, not because they wait for green.

**Evidence.** *Opinion* corrected by our own measurement.

**Addresses.** PR-12's required-by date; auto-issue after three consecutive reds.

**Cost.** Low: a `required_by:` field and a scheduled test that fails when the date passes.

**Failure mode.** Deadlines extended as a formality; an extension needs a written reason on
the issue, the rule CLAUDE.md already has for closing by hand.

---

## 3. Domain rules 5.4% and clocks / lifecycle 5.7%

### 3.1 Approval (golden-master) testing on operator-approved outputs

**What.** State the output you care about, have a person approve it once, fail when it
changes, and on failure open a diff to approve or fix ([ApprovalTests](https://approvaltests.com/);
[Python](https://pypi.org/project/approvaltests/)).

**Evidence.** *Adopted*; long practice record, no controlled study.

**Addresses.** domain_rule (golden real-data diff: 23 of 32 fixes, 36 of ~159 Purser items);
PR-06. Privacy maps directly: the approved file is rule ids, row ids and pass/fail, never
amounts, git-excluded on the operator's machine; CI runs the same checker on a planted ledger.

**Cost.** Low–med: one checker, one approved file per surface, a minute locally before a
close; the operator approves once instead of re-finding the same wrong number each release.

**Failure mode.** Blind approval: "most developers, upon seeing a snapshot test fail, will
sooner just nuke the snapshot and record a fresh passing one" ([Dodds, Effective Snapshot Testing](https://kentcdodds.com/blog/effective-snapshot-testing)).
Guards: small named files, a non-zero expectation per figure (the $0-satisfiable demo,
#2215), and re-approval that names what changed.

### 3.2 Specification by example, example mapping, decision tables

**What.** Adzic's seven patterns: derive scope from goals, specify collaboratively,
illustrate with examples, refine, automate validation without changing the specification,
validate frequently, evolve living documentation ([Specification by Example](https://www.oreilly.com/library/view/specification-by-example/9781617290084/)).
Example mapping is the 25-minute version: story, rules, examples, questions
([Cucumber blog](https://cucumber.io/blog/bdd/your-first-example-mapping-session/)). A
decision table is the oldest form: conditions as rows, each column a rule, actions below
([ISTQB glossary](https://istqb-glossary.page/decision-table/)).

**Evidence.** *Adopted* (50+ qualitative case studies).

**Addresses.** domain_rule and spec_gap. The trips-rulebook §15 "Measured-on / Refused-by"
table is a decision table with examples and the most defect-aware document in the corpus; the
fallback branch it did not table (#2222) is the predicted failure.

**Cost.** Low: a rule table per concept, each row an example that becomes a test; operator
time capped at 25 minutes per story.

**Failure mode.** Examples written by the agent alone are its assumptions in table form; the
operator supplies or approves them — 3.1's approved file, authored before the build.

### 3.3 Property-based testing (Hypothesis)

**What.** State a property for all inputs; the library generates and shrinks. Stateful
testing drives a `RuleBasedStateMachine` and checks `@invariant`s after each step
([Hypothesis](https://hypothesis.readthedocs.io/); [stateful](https://hypothesis.readthedocs.io/en/latest/stateful.html)).

**Evidence.** *Adopted*; mature, wide use.

**Addresses.** PR-06's oracle ("a card equals the sum of its drill rows", "surfaces agree")
is a property; so are month arithmetic across year ends, sign per account kind, and
pagination that walks past the default limit (#2220, 88e3a8a592).

**Cost.** Low–med: more CPU (bounded by `max_examples`), one idiom for agents to learn.

**Failure mode.** Properties that restate the implementation; slow tests that get skipped.
Scope to PR-07's registered concepts.

### 3.4 One owner per invariant (DDD aggregates)

**What.** "Model true invariants in consistency boundaries": an aggregate is the one place a
rule is kept consistent, and a rule in two places is two rules ([Vernon, Effective Aggregate Design I](https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_1.pdf)).

**Evidence.** *Opinion*, canonical in its field.

**Addresses.** PR-07: income x4, ledger frontier x6–7, month arithmetic x8–10 are invariants
without an aggregate. The concept registry is Vernon's rule as a table; 1.7 is how it fails.

**Cost.** Low per PR once the registry exists.

**Failure mode.** A registry with no owner function and no pinning test per row is prose.

### 3.5 Injectable, named clocks

**What.** The `java.time.Clock` javadoc states it as policy: "Best practice for applications
is to pass a Clock into any method that requires the current instant", so a fixed or offset
clock can be used in tests ([Clock, Java SE 8](https://docs.oracle.com/javase/8/docs/api/java/time/Clock.html)).
Fowler lists system-clock calls among the five causes of non-determinism (2.1).

**Evidence.** *Adopted* (platform documentation; present in every mature date library).

**Addresses.** state_lifecycle (pinned clocks: 22 of 43): the clock seam re-fixed seven times,
`when_for(None)` expiring a corpus, Pulse on UTC (#2232). PR-08 goes past the javadoc by
**naming** the clock (data frontier, wall clock, pinned as-of, member timezone), which no
published practice does.

**Cost.** Low: a lint forbidding `datetime.now()` / `Date.now()` outside the clock module;
two pinned clocks per engine test.

**Failure mode.** An injectable clock defaulted to the wall clock is the bug with a
parameter; roots inject explicitly and the boot smoke asserts which clock each composed.

---

## 4. Error handling 6.8% and UI truthfulness 4.9%

### 4.1 Errors as values the compiler forces you to handle

**What.** Rust's `Result` is `#[must_use]`: ignoring one is a warning, "because ignoring an
error value can hide a failed operation" ([std::result](https://doc.rust-lang.org/std/result/)).
Go: "errors are values", programmable rather than checked by rote ([Pike, 2015](https://go.dev/blog/errors-are-values)).
In TypeScript, `neverthrow` supplies `Result` and `eslint-plugin-neverthrow/must-use-result`
fails lint unless a `Result` is consumed by `.match` / `.unwrapOr` / explicit unsafe unwrap
([eslint-plugin-neverthrow](https://github.com/mdbetancourt/eslint-plugin-neverthrow)).

**Evidence.** *Adopted*; Rust's is language-wide.

**Addresses.** error_handling (raising stub: 30 of 52): 42 of ~90 `useLoad` sites ignoring
the error (#2240), fallbacks returning absent / -1 / healthy, a 404 caught into simulated
success (c4331de4ee); PR-05's "`?? []` fails lint".

**Cost.** Low–med: one hook type, one lint rule, a migration of existing sites.

**Failure mode.** `unwrapOr(default)` everywhere is `?? []` with a longer name; lint treats
an empty/zero/healthy default on a load result as the error it is. 4.3 gives the error branch
somewhere to go.

### 4.2 Make illegal states unrepresentable

**What.** A sum type for `loading | loaded | failed | not-composed` instead of booleans and
nullables, so invalid combinations cannot be built ([Minsky's maxim, written up by Wlaschin](https://fsharpforfunandprofit.com/posts/designing-with-types-making-illegal-states-unrepresentable/)).

**Evidence.** *Opinion*, widely adopted in typed languages.

**Addresses.** ux_truthfulness: "ALL QUIET" over a 503 (#2238) and "ALWAYS ON" with no
sender (#2231) are representable illegal states; PR-05's state as a discriminated union makes
the compiler reject the lie.

**Cost.** Low; TypeScript exhaustiveness.

**Failure mode.** A `default:` branch re-admits every illegal state; lint exhaustiveness.

### 4.3 The UI stack: a story and a test per state

**What.** Every screen has blank, loading, partial, error and ideal states; the transitions
are where products "feel weird" ([Hurff, the UI stack](https://www.scotthurff.com/posts/why-your-user-interface-is-awkward-youre-ignoring-the-ui-stack/)).
Storybook renders a story per state; a `play` function drives and asserts in a real browser
([Storybook, interaction tests](https://storybook.js.org/docs/writing-tests/interaction-testing)).

**Evidence.** *Opinion* plus *adopted* tooling.

**Addresses.** PR-05's screen × state matrix; 12 screens hanging on "Loading…"; the
feature-off state nobody specified (#2213). Our list is longer than Hurff's (401/expired,
503-disabled, backend-not-mounted, 375 px, back/reload) because our defects say so.

**Cost.** Med: many story files, cheap for agents, generated from the state union in 4.2; a
1–2 minute runner per PR.

**Failure mode.** Stories against a mock handing over a pre-made "error" object never
exercise the **transition** from a real rejection (design-gui.md §6 specified every state;
#2240 shipped). The stub client must reject, 503 and time out.

### 4.4 End-to-end journey regression (Playwright)

**What.** `toHaveScreenshot()` compares to a reference, retries "until two consecutive
captures are identical" and disables animations; fonts and mid-render capture are the named
flake sources ([Playwright, visual comparisons](https://playwright.dev/docs/test-snapshots)).

**Evidence.** *Adopted*; the maintainers' own guidance.

**Addresses.** ux_truthfulness and ui_behavior (e2e: 15 of 33 and 22 of 31). The Purser
walkthrough is the one gate here that caught honesty regressions.

**Cost.** Med–high: browser, served build, seeded database, 2–6 minutes, and the most
attention-hungry failures when it flakes. Required only on frontend/server paths.

**Failure mode.** Measured here: geometry/pixel assertions across renderers gave 216
failures and 0 defects. What survives is **text and effect after a click** (PR-04), with
screenshots kept as artifacts for the operator's walk, not as assertions.

---

## 5. Security at seams 8.5%

### 5.1 Deny by default and a per-route authorization matrix

**What.** "If a request is not specifically allowed, it is denied"; if access-control code
throws, "access control should always be denied"; and "create tests that validate that the
permissions mapped out in the design phase are being correctly enforced"
([OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)).

**Evidence.** *Adopted* standard (Broken Access Control is OWASP Top 10 A01:2021).

**Addresses.** PR-14: anonymous requests served as a member (#2229), any member minting a
grant for another (#2235), offboarding residue (#2359–#2365).

**Cost.** Low–med: a route inventory generated from the router, an actor × action matrix, a
parametrised test (unauthenticated → 401, other member → 403) over the composed fleet; under
a minute.

**Failure mode.** A hand-kept matrix drifts from the router; generate it and fail on an
unlisted route.

### 5.2 RLS tested under the production role

**What.** Superusers and `BYPASSRLS` roles bypass row security; owners bypass it unless
`FORCE ROW LEVEL SECURITY` ([PostgreSQL, Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)).
Supabase's pgTAP pattern sets `local role authenticated` and the JWT claims, then asserts
both allowed and denied operations per table ([Supabase, testing](https://supabase.com/docs/guides/local-development/testing/overview)).

**Evidence.** *Adopted* (vendor documentation).

**Addresses.** PR-13: nine tables with no policy passing under the superuser (605eb1fc10),
P0s #2414/#2419, two wrong security conclusions from superuser probes.

**Cost.** Low once the fixture default flips (1.4); each test prints `current_user`,
`rolsuper`, `rolbypassrls` and the tenant GUC beside its result.

**Failure mode.** The right role but the **owner** without `FORCE`; vendor-semantics
premises (`RESET` leaving an empty string, 18bc907fd2) unrecorded with their version.

### 5.3 STRIDE per element, with routes as the elements

**What.** Enumerate threats per data-flow element — external entities face spoofing and
repudiation, stores tampering/disclosure/denial, processes all six — so non-experts can
threat-model systematically ([Shostack, Experiences Threat Modeling at Microsoft](https://shostack.org/files/papers/modsec08/Shostack-ModSec08-Experiences-Threat-Modeling-At-Microsoft.pdf)).

**Evidence.** *Adopted* at scale; two-pass STRIDE in #1580 found three issues neither pass
held alone.

**Addresses.** The category-level STRIDE that missed per-route authorization (#2235): each
mounted route and credential-minting lever is an element; 5.1's matrix is the enumeration.

**Cost.** Med at design time, once per trust-boundary design, two rounds (PR-18); nothing
per PR.

**Failure mode.** STRIDE against a diagram has no stopping point; against the generated
route list every row is covered by a test or is a finding.

---

## 6. Done and scope

### 6.1 Definition of Done as a commitment

**What.** "A formal description of the state of the Increment when it meets the quality
measures required for the product"; an item that does not meet it "cannot be released or
even presented at the Sprint Review" ([Scrum Guide 2020](https://scrumguides.org/scrum-guide.html)).

**Evidence.** *Adopted.*

**Addresses.** PR-09, PR-11: milestones closed on issue count (#1064), demos closed "not
re-run", 189 UAT issues filed days after release. "Cannot even be presented" is the
mechanism: the completion gate refuses a close without the demo artifact at the closing SHA.

**Cost.** Low; the walkthrough already produces the log.

**Failure mode.** A DoD of activities instead of observations; every line names a door and an
instrument, which `acceptance_check` can enforce.

### 6.2 BDD / Gherkin: keep the examples, not the language

**What.** Cucumber "is not a testing tool" but "a tool for capturing common understanding",
and the misuse is treating scenarios as a scripting language ([Hellesøy, 2014](https://cucumber.io/blog/collaboration/the-worlds-most-misunderstood-collaboration-tool/));
Given/When/Then should be derived from real conversations, not forced
([Keogh, 2014](https://lizkeogh.com/2014/09/01/deriving-gherkin-from-real-conversations/)).

**Evidence.** *Opinion* from the practice's originators; the failure mode is widely reported.

**Addresses.** Layer 2's acceptance lines, negatively: imperative steps couple to the UI and
explode step definitions. Keep the example (3.2) as a table row or a planted-household test.

**Cost.** Avoided.

**Failure mode (of adopting).** A second language owned by nobody, turning into change
detectors (2.3).

### 6.3 Demo-driven acceptance and dogfooding: the operator is the oracle

**What.** A person watching the running system do the task; dogfooding is the continuous
form.

**Evidence.** *Measured locally*: the operator on real data found 27.4% of fixes, audits
16%, CI 8.3%. No controlled study of dogfooding surfaced; our numbers are the evidence.

**Addresses.** Layer 6; PR-11; only 4 of 645 self-corrections came from looking at a screen.

**Cost.** Operator time, the scarcest input: one task, one target, one SHA per walk, and the
agent produces its own walk artifact **before** asking for the operator's.

**Failure mode.** Audits standing in for use: several apps were never mounted for anyone. An
app with no user is not done at any issue count.

### 6.4 WIP limits

**What.** WIP limits are "an enabling constraint" that creates a pull system; limiting entry
is "key to reducing delay and context switching which may result in poor timeliness, quality,
and potentially waste" ([Kanban University, Official Guide](https://kanban.university/kanban-guide/)).
Little's Law (lead time = WIP ÷ throughput) is the arithmetic.

**Evidence.** *Adopted*; Little's Law is a theorem for stable queues.

**Addresses.** Layer 6: 14 apps, four mounted nowhere, three fronts in one CLAUDE.md edition.

**Cost.** Negative for throughput; the mechanism is the `claim` hook refusing a second app
while the first has no user.

**Failure mode.** A limit written as prose ("one active front") that the next session
re-cuts; it must be a count in a file a hook reads.

### 6.5 Trunk-based development and small batches

**What.** Merge to trunk at least daily; "when developers know they can get their code into
trunk without a great deal of ceremony, the result is small code changes that are easy to
understand, review, test" ([dora.dev](https://dora.dev/capabilities/trunk-based-development/));
small batches "counteract the risk of instability as AI accelerates development"
([dora.dev](https://dora.dev/capabilities/working-in-small-batches/);
[trunkbaseddevelopment.com](https://trunkbaseddevelopment.com/)).

**Evidence.** *Measured* (survey-correlational, tens of thousands of responses).

**Addresses.** Layer 9's ceremony inversion: "one PR per line of work, slices are commits" is
a small-batch rule; the 35% ceremony share is the ceremony DORA names.

**Cost.** Negative once the local gate is trusted: push, one PR, arm auto-squash, stop.

**Failure mode.** Without PR-01 and PR-20, trunk takes semantic conflicts two green branches
hide (the ENFORCED/LEGACY case).

### 6.6 Appetite, not estimate

**What.** "Estimates start with a design and end with a number. Appetites start with a
number and end with a design"; fixed time, variable scope ([Basecamp, Shape Up](https://basecamp.com/shapeup/shape-up.pdf)).

**Evidence.** *Opinion*, one company's practice.

**Addresses.** 153k words of design for ~10k lines; seven revisions of one dossier. An
appetite on design (one authoring pass, one adversarial pass) and on a release (the demo, not
the issue list) replaces open-ended refinement.

**Cost.** None per PR.

**Failure mode.** Scope cut until the demo is satisfiable by nothing; PR-11's non-zero
oracle bounds the cut.

---

## 7. Documentation volume against outcome

### 7.1 Architecture Decision Records

**What.** One page — context, decision, consequences, status — beside the code, because "no
one reads large documents" ([Nygard, 2011](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions);
[adr.github.io](https://adr.github.io/)).

**Evidence.** *Adopted* (Thoughtworks Radar "Adopt"); no defect-effect study.

**Addresses.** The right **size** for the documents that worked here (the egress §0 threat
model, the two-lease ADR with its strict-xfail test).

**Cost.** Low. Rule to add (PR-19): a behaviour claim cites a test or carries UNVERIFIED; 17
of ours say Proposed while implemented, so status is derived or dropped.

**Failure mode.** ADR as changelog: the Purser design's §11 is 24.9k words of dated
amendments, ADRs without the page limit.

### 7.2 Design docs and RFDs at real companies, and when not to write one

**What.** Oxide's RFDs are AsciiDoc in a repo, iterated on a branch, discussed as a PR, 500+
in five years ([Oxide, RFD 1](https://oxide.computer/blog/rfd-1-requests-for-discussion)). At
Google the decision "comes down to deciding whether the benefits in organizational consensus,
documentation, and senior review outweigh the extra work", and the test is whether "the
solution to the design problem is ambiguous" ([Ubl, Design Docs at Google](https://www.industrialempathy.com/posts/design-docs-at-google/)).

**Evidence.** *Opinion* (two companies).

**Addresses.** Layer 3's "the few doc templates that earn their place". Both exist for
organisational consensus, which a solo developer does not need; what remains is the seam
table, the threat model against code, and the rule table with examples — the forms that
caught defects here.

**Cost.** Fewer documents; Ubl's test per feature: ambiguous → one-page design; otherwise the
issue's done-when is the design.

**Failure mode.** Review against documents has no stopping point (rounds 7–12 in one day).
One adversarial round, terminated against code — in CLAUDE.md, enforced nowhere.

### 7.3 Working software; living documentation

**What.** The Agile Manifesto's second value ([agilemanifesto.org](https://agilemanifesto.org/)).
Documentation should change "at the same pace as software design and development",
generated from code and tests where possible ([Martraire, Living Documentation](https://books.google.com/books/about/Living_Documentation.html?id=8_6ZDwAAQBAJ));
Adzic reserves "living documentation" for executable specifications, as against printed ones
"which quickly get outdated" (3.2).

**Evidence.** *Opinion*, two decades of adoption.

**Addresses.** Layer 5 (catalogue generated from code with reachability) and PR-19; 31% stale
status rows.

**Cost.** Med once (generators); zero attention after.

**Failure mode.** Generated documents committed and hand-edited (the render-train lesson);
generate on read or fail the diff.

### 7.4 What research says about documents and defects

**What.** Practitioners do not update documentation "as timely or completely as software
process personnel and managers advocate"
([Lethbridge, Singer & Forward, IEEE Software 2003](https://www.researchgate.net/publication/3247967_How_Software_Engineers_Use_Documentation_The_State_of_the_Practice)).
Across 878 documentation issues, up-to-dateness was the largest content problem
([Aghajani et al., ICSE 2019](https://dl.acm.org/doi/10.1109/ICSE.2019.00122)). On review:
"reviews are less about defects than expected", more about knowledge transfer and
understanding ([Bacchelli & Bird, ICSE 2013](https://dl.acm.org/doi/10.5555/2486788.2486882)).

**Evidence.** *Measured* on staleness and review outcomes. **No study found this session
links documentation volume to defect rate** either way; our own trace (26% correct and
missed, 17% prescribed the defect, 39% silent) is the only quantitative evidence on hand.

**Addresses.** Posture: staleness is the measured risk, so every behaviour claim cites a test
or is marked; review's measured value is understanding, which argues for the **adversarial**
pair (9 distinct must-fix defects in 46 reviews) over a cooperative pass.

**Cost.** None.

**Failure mode.** Reading "docs do not prevent defects" as "write none". The documents that
worked were short, checked against code, and had an oracle.

---

## 8. Ranked top twelve for our situation

Ranked by share × evidence ÷ per-PR cost. Shares overlap.

| # | Practice | Share | Evidence | Per-PR cost | Serves |
|---|---|---|---|---|---|
| 1 | Required boot smoke of every real root: production role, migrate-from-previous, boot twice, one request per route/nav/schedule (1.3, 1.4) | 19.5% | adopted + our 130 | 2–5 min | PR-01/02/10 |
| 2 | Schema-first codegen with a diff gate; one declaration per identifier; emit/consume test (1.1) | 11.9% | adopted | seconds | PR-15 |
| 3 | Config declared once, validated at startup, parity derived (1.5) | 10.5% | adopted | < 1 s | PR-03 |
| 4 | Harness as product: planted defect, FP count, OS/shell case, required-by date, auto-issue on 3 reds (2.1, 2.2, 2.5) | 15.4% | measured | minutes per gate change | PR-12 |
| 5 | Must-use error values, unrepresentable illegal states, screen × state matrix against a rejecting stub (4.1–4.3) | 11.6% | adopted + opinion | lint seconds; stories 1–2 min | PR-05 |
| 6 | Operator-approved golden answers, real-data diff local, planted-ledger parity in CI (3.1, 3.3) | 11.0% (with 7) | adopted; our 23 of 32 | 1 min before a close | PR-06 |
| 7 | Concept registry with owner gate; named injectable clocks (1.7, 3.4, 3.5) | with 6 | adopted | sub-second | PR-07/08 |
| 8 | Route matrix generated from mounted routes; RLS under the production role, identity printed (5.1, 5.2) | 8.5% | adopted | < 1 min | PR-13/14 |
| 9 | Real-backend e2e: click every control, assert effect after reload; text, never pixels (4.4) | 13.5% | adopted; our 216-for-0 | 2–6 min on UI/server paths | PR-04 |
| 10 | Done = demo artifact at the closing SHA on the named target; door and instrument per acceptance line (6.1, 6.3) | 11.1% | adopted + our 27% | one walk per milestone | PR-09/11 |
| 11 | Cold two-voice adversarial review, two rounds, judged against code; STRIDE with routes as elements (5.3, 7.4) | 17.4% | measured + our 9 in 46 | one dispatch per PR | PR-18 |
| 12 | WIP limit as a hook-read count; one PR per line of work; appetite on design; ceremony inverted (6.4–6.6) | process-wide | measured (DORA) | negative | layers 6, 9 |

Unranked but load-bearing: PR-20's merged-tree test; mutation testing on changed lines (2.2)
as the instrument behind #4; second-consumer extraction (1.6) for new toolboxes.

---

## 9. Sounds right; the evidence does not support it

- **Coverage thresholds.** Low-to-moderate correlation with fault detection
  ([Inozemtseva & Holmes](https://dl.acm.org/doi/10.1145/2568225.2568271)). Use coverage
  only to find never-executed code.
- **Gherkin as the acceptance format.** Not a testing tool, per its creator
  ([Hellesøy](https://cucumber.io/blog/collaboration/the-worlds-most-misunderstood-collaboration-tool/));
  imperative scenarios become change detectors. Keep the examples.
- **A Pact broker for one operator's fleet.** Pact's value is independent deploys of
  separately owned services ([Pact](https://docs.pact.io/getting_started/what_is_pact_good_for));
  codegen plus a schema diff gives the protection at a fraction of the cost.
- **Pixel or geometry regression across renderers.** Fonts and mid-render capture are the
  maintainers' own flake sources ([Playwright](https://playwright.dev/docs/test-snapshots));
  here, 216 failures and 0 defects.
- **A mutation-score target.** Equivalent mutants make 100% unreachable; Google surfaces
  individual mutants on changed lines instead ([Petrović & Ivanković](https://research.google.com/pubs/archive/46584.pdf)).
- **Large frozen designs reviewed against other documents.** No evidence links volume to
  fewer defects; staleness is the measured risk ([Lethbridge](https://www.researchgate.net/publication/3247967_How_Software_Engineers_Use_Documentation_The_State_of_the_Practice);
  [Aghajani](https://dl.acm.org/doi/10.1109/ICSE.2019.00122)); our documents prescribed the
  defect in 17% of traces.
- **Snapshot tests as a safety net.** Approved blindly under pressure ([Dodds](https://kentcdodds.com/blog/effective-snapshot-testing));
  golden masters work only as small, named, person-approved outputs with a non-zero expectation.
- **"Report-only until green, then required."** Nobody watches an unrequired job (101 of
  101, 102 of 102). Bound it by date ([Fowler](https://martinfowler.com/articles/nonDeterminism.html)).
- **More rules in CLAUDE.md, memory or a primer.** Reminders are signage
  ([Norman](https://jnd.org/preface-design-of-everyday-things-revised-edition/)); 22 of 32
  rules prose-only, 35% of corrections repeated a written rule.
- **Cooperative code review as the defect filter.** Reviews are "less about defects than
  expected" ([Bacchelli & Bird](https://dl.acm.org/doi/10.5555/2486788.2486882)); give
  defect-finding to the adversarial voice and the integration gates.
- **Platform first.** Monolith-first and the wrong abstraction ([Fowler](https://martinfowler.com/bliki/MonolithFirst.html);
  [Metz](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction)): extract on the second
  wired consumer, not before.
- **Trusting a sense of speed or completion.** A 39-point gap between believed and measured
  speedup ([METR](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)).
  Statements need receipts; done needs a walk artifact.

---

## Caveats

- Evidence is uneven: *measured* entries come from populations unlike a solo developer with
  agents; *adopted* entries are maintainers describing their own tools. Per-PR costs are
  estimates, to be measured in the first week as CLAUDE.md requires of any gate.
- Two PDFs were read by text extraction: the Google mutation figures were confirmed; the Luo
  et al. percentages were not and are omitted. The Micco blog served only its comments, so
  flakiness thresholds are cited from the Google engineering book.
- No controlled study of dogfooding or of documentation volume against defect rate was found;
  those sections say so.
- No household data appears here; every example is a sha, an issue number or a process fact
  already in the evidence report.
