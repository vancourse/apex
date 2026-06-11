# apex full-lifecycle roadmap — closing the ends of the pipeline

*2026-06 deep review of apex 0.3.8: where the framework is strong, where the lifecycle has holes, what ships in wave 1, and what is deliberately deferred or rejected. Companion to `sdlc-frameworks-survey.md` (which compared apex against other frameworks; this compares apex against the full software lifecycle).*

## The finding in one paragraph

apex 0.3.8 is **vertically excellent and horizontally complete in the middle**: every artifact between "idea" and "merged PR" has an author step, an adversarial review, and a freeze (PRD → design → impl-plan → code), the horizontal consistency layer exists (`cross-artifact-consistency`), and the post-release *learning* loop exists (`incident-retro`, `autonomous-fix`, `investigate-bug`). But the pipeline has hard edges at both ends. **Before** the pipeline: apex assumes an existing repo — there is no greenfield path (the survey's adopts all improved existing gates; none created the rig the gates run in). **After** phase 7: merged ≠ shipped — no release event for user projects, no CI/CD authoring gate (apex *probes* CI in `detect-stack` and *ships* one reference template in `autonomous-fix`, but never reviews a pipeline), no deploy/IaC gate (architecture-design Pass 4 *chooses* a deploy model once; nothing audits the changes that implement it). Orthogonally: UI work has a failure mode no gate catches (visually wrong code that passes every test — nobody *looked*), and the review mechanic tops out at two voices with no operability seat and no model-routing rule.

## Wave 1 — shipped with this roadmap

Six skills + two commands + one hook tightening. Each composes existing gates rather than duplicating them; each carries a YAGNI guard.

| Gap | Skill | Entry | Composes |
|---|---|---|---|
| Greenfield + adopt | `project-bootstrap` | `/apex:new` | `architecture-design` (P1), `cicd-review` (P4), `/apex:prd` (P5 walking skeleton) |
| Release event for user projects | `release-readiness` | `/apex:release` | `data-migration-review` (migration notes), `observability-review` (bake signals), `incident-retro` (bad bake) |
| Pipeline-as-code | `cicd-review` | [AUTO] on workflow-file edits (hook) / by name | `test-strategy` (CI tiers), `security-review` boundary stated |
| Deploy + IaC | `deployment-review` | [AUTO]/by name | `architecture-design` Pass 4 (instantiates per-change), `data-migration-review` (sequencing), `cicd-review` (the pipeline that runs it) |
| UI visual correctness | `ui-design-review` | [AUTO]/by name | `rules/frontend.md` (enforces it), `verification-before-completion` (extends to pixels), `test-strategy` Layer 7 |
| High-stakes review depth + model routing | `council-review` | by name, 4 named cases only | `adversarial-pair` (extends 2→3 seats), `spec-view` (human tiebreak) |

Design notes that mattered:

- **The SHIP phase.** `release-readiness` + `deployment-review` give FLOW.md a phase 8 — the pipeline previously ended at REVIEW + memory-note. Release answers *whether/what*; deployment answers *how it reaches the environment*; data-migration keeps owning *the data inside the window*. Three skills, three non-overlapping contracts.
- **Council ≠ persona swarm.** The survey explicitly rejected BMAD's persona swarm. The council survives that rejection by construction: seats *review* one frozen-candidate artifact (never author), three is a hard cap, one round only, and convening is restricted to four named freeze cases. Its genuinely new contributions: the operability/simplicity seat (the pair's blind spot), the disagreement-goes-to-human-verbatim rule, and the model-routing table (deep-reasoning for the adversary; a fast model never decides a freeze).
- **Bootstrap owns the rig, not the decisions.** `project-bootstrap` routes all decisions to `architecture-design` and all pipeline review to `cicd-review`; its own value is the official-generator rule (hand-rolled skeletons fossilize), the docs/-convention wiring, and the walking-skeleton discipline (one PRD queued, no backlog seeding). ADOPT mode touches nothing but the wiring.
- **The hook does the routing.** `suggest-skill-on-edit.sh` now pattern-matches CI/CD paths (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml`, `.circleci/`) the way it already matched API paths — `cicd-review` fires where the work happens, no new ambient cost.

## Wave 2 — adopt next, in order

1. **`performance-review`** (design-phase, conditional). The latency budget twin of `observability-review`: critical-path budget stated, hot layers named, N+1/cardinality risks walked, load assumptions tested against the design — fires only when the feature has a hot path or a data-volume axis. (observability-review audits whether you can *see* slowness; nothing audits whether the design *will be* slow.)
2. **Pre-mortem** (survey adopt #4, still unbuilt). Cheapest remaining survey item: a one-page "it's six months later and this project failed — why?" pass at the impl-plan freeze. Probably a counter-pass amendment to `impl-plan-review`, not a skill.
3. **`docs-review`** (ship-phase, conditional). For released surfaces: README quickstart actually runs, API docs match the surface (`api-surface-review`'s consumer lens, applied to prose), migration guide exists for every MAJOR bump. Conditional on having external consumers.
4. **Profile-driven model routing.** Extend `apex.profile.toml` (detect-stack's artifact) with an optional `[models]` table so council seats and heavy review passes can name real model bindings per project, the way tracker/observability axes already bind tools. Defer until councils are actually convened with multiple model families.
5. **`cost-review`** (conditional pass, likely inside `deployment-review` or `architecture-design` Pass 4 amendment). Cloud-bill blast radius of an infra change: the three cost-dominant resources named, the runaway guard (budget alert) stated. Not a FinOps practice — one adversarial question.

## Explicitly rejected (and why)

- **Cloud-specific deploy skills** (`azure-deploy`, `aws-deploy`). `deployment-review` states the platform-neutral rule first with per-cloud notes where mechanics differ (OIDC variants). Per-vendor skills would fossilize console walkthroughs apex can't keep current — the same staleness argument as `verify-ports`.
- **Shipping IaC/pipeline templates beyond the existing autonomous-fix reference.** The survey's SBOM/Sigstore rejection generalizes: apex asks review questions; the host project wires tools. One reference template (autonomous-fix) exists because its *conformance-lint* is the product; a template library is a maintenance treadmill.
- **N>3 council seats / multi-round debate.** Seats beyond three add correlation, not coverage; debate rounds average disagreements into mush — the disagreement IS the signal. Cap is structural.
- **A backlog/board system in bootstrap.** The walking skeleton is the backlog until it ships. Tracker discipline belongs to the project's tracker (detect-stack already routes to it).
- **DORA/SPACE measurement of the new phases** — re-affirming the survey's rejection; no dashboards.

## The agent-first audit — apex's consumer is Claude Code, not the human

apex's stated purpose is to let a coding agent produce **production-strength code at scale, autonomously**. Reviewed end-to-end with that lens (the human never reads the MD files; the agent must execute them), five structural findings, ranked:

1. **Phase state lives in prose, not in a machine-decidable place.** "Is the PRD frozen?" is answered today by reading `❄️ FROZEN 2026-06-06` in a doc header — fine for one session, undecidable across sessions/agents. An autonomous agent resuming a feature must re-derive pipeline position from conversation context it no longer has. **Fix (wave 2, highest priority): a per-feature machine-readable state block** — frontmatter on each artifact (`status: frozen`, `frozen_at`, `gate: prd-review`) plus one `docs/<feature>/state.json` the gates update — so "which phase am I in, what's frozen, what gate is next" becomes a file read, not an inference. This is the autonomous-operation primitive everything else stands on.
2. **Advisory-heavy enforcement assumes an attentive agent.** Only 2 of 10 hooks hard-block (secrets, destructive bash); the rest nudge — and a nudge an agent can ignore under context pressure is not a rail. The `autonomous-fix` conformance-lint shows the right pattern: a **decidable check** instead of a reminder. Extend it: lint that a PRD has scenario IDs + layer tags before `frozen` may be set; lint that a design carries `realizes S#` tags; lint that an impl-plan names a scenario per layer (`cross-artifact-consistency` already parses these — the lint is its Pass 1 run as a gate, not a report). Freezing becomes *blocked* on shape, not suggested.
3. **Routing is keyword-regex; firing conditions are prose.** `suggest-skill-on-prompt`/`-on-edit` pattern-match strings; each SKILL.md states "when to fire" in English. Wrong phrasing → silent gate miss, the failure mode that matters most when nobody is watching. **Fix: a machine-readable gate registry** — one `gates.json` (skill → phase → firing predicate → blocking?) generated from the matrix in FLOW.md, consumed by hooks and by the agent at phase transitions. FLOW.md's ASCII art stays for humans; the agent reads the registry.
4. **Context economics at 43 skills.** The skills total ~10k+ lines; an agent that loads the wrong three burns the budget the review needed. The routing-table idiom (python-review's "never load all rule files") and `apex-terse` are the right instincts — but per-skill, ad hoc. Generalize: every SKILL.md's frontmatter `description` is the router (already true); add a one-line `cost:` hint (cheap/medium/heavy) and keep pass bodies lazy-loadable. Council/pair dispatch already isolates context per seat — that pattern (narrow context per reviewer) is the scaling mechanism; name it as the default for every heavy gate.
5. **The bounded-loop pattern is right — finish applying it.** Copilot 5-round cap, screenshot ≤3 rounds, council 1 round, fail-closed cost caps in autonomous-fix: every loop an autonomous agent runs needs a terminal state and a budget. Unbounded today: the design→review→amend cycle (an agent can ping-pong design-review findings indefinitely) and verification retries. Give each a cap + an escalate-to-human terminal, same as the Copilot loop.

What does NOT need to change: artifact-freeze-as-contract is exactly right for agents (frozen artifacts are the cross-session memory); composition-over-duplication keeps the gate graph small enough to route; the YAGNI guards prevent the agent from drowning itself in its own ceremony.

## Holes this roadmap leaves open, knowingly

Multi-region/DR design, SRE error budgets, on-call rotation discipline, customer comms during incidents (incident-retro deliberately excludes response), compliance regimes (SOC2/HIPAA evidence trails), and design-tool handoff (Figma-to-code). Each is real, each is org-altitude or tool-specific in the way the survey's reject list warns about. Revisit only when a consuming project hits the wall in practice.
