# Design — `agent-rails` (machine-decidable pipeline state + freeze enforcement + gate registry)

**Status:** DRAFTED — awaiting `design-review` + user sign-off · **Upstream:** `prd.md` (FROZEN, PR #27)
Resolves U1–U5 and carries F5 from `prd-review.md`. Realizes S1–S7.

---

## 1. Shape — one skill, three files, no daemon

Everything ships inside **one new skill, `agent-rails`** ([AUTO] at phase transitions / by name; no new slash command), following the `autonomous-fix` pattern: a SKILL.md discipline + `reference/` scripts + a CI conformance workflow.

| Piece | Lives at | Role |
|---|---|---|
| `state.json` | `docs/<slug>/state.json` (per feature, committed) | gate-state record — *realizes S1, S3, S4, S7* |
| `gates.json` | repo root, beside `FLOW.md` | the queryable registry — *realizes S5* |
| `reference/state_tool.py` | `skills/agent-rails/reference/` | read/report/transition CLI (stdlib only) |
| `reference/freeze_lint.py` | `skills/agent-rails/reference/` | shape lint gating `frozen` — *realizes S2* |
| `reference/registry_check.py` | `skills/agent-rails/reference/` | gates.json ↔ FLOW.md matrix conformance — *realizes S6* |
| `.github/workflows/agent-rails-conformance.yml` | apex CI | runs lint fixtures + registry check |

JSON, not TOML, deliberately: `apex.profile.toml` is human-edited config (TOML's niche); `state.json` is machine-written *evidence* — stdlib `json`, no comments wanted, hash-friendly. (Closes the prd-review counter-pass item 4.)

## 2. `state.json` — schema (resolves U2: minimal, evidence-only)

```json
{
  "version": 1,
  "feature": "agent-rails",
  "artifacts": {
    "prd":       { "status": "frozen", "gate": "prd-review", "at": "2026-06-11",
                   "sha256": "<content hash at freeze>", "signed_off_by": "PR #27" },
    "design":    { "status": "in-review" },
    "impl-plan": { "status": "absent" }
  }
}
```

- **Statuses:** `absent → draft → in-review → frozen` (+ derived flags the *tools* report but never store: `DIVERGENCE`, `POST-FREEZE-DRIFT`, `MALFORMED-TRANSITION` — flags are computed fresh each read, S4/S7's "never auto-heals, never stored truth").
- **Evidence fields (`gate`, `at`, `sha256`, `signed_off_by`) are mandatory iff `status: frozen`** — their absence on a frozen entry IS the S7 MALFORMED-TRANSITION signal. Nothing else is stored: pass results, findings, and rationale stay in the prose review docs (U2's minimality).
- **Hash = sha256 of the artifact's bytes at freeze.** Any byte change afterwards — including a formatter pass — flags POST-FREEZE-DRIFT. Deliberate: "the frozen artifact changed" is exactly the event the freeze discipline wants surfaced; an amendment re-freezes with a new hash. Stated here so nobody "fixes" the lint to ignore whitespace later.
- **Writes are atomic** (temp file + `os.replace`, same-directory — the `detect-stack` writer pattern), realizing S3's torn-write edge.

## 3. Sign-off representation (resolves U3 — the honest option)

`signed_off_by` records **the PR number whose merge constituted sign-off** (`"PR #27"`), because in this repo's actual workflow the human's merge IS the sign-off act. Strength, stated honestly per the PRD's requirement:

- **In-repo, the field is fabricatable** — an agent can type `"PR #99"`. The lint checks *form*, not authority (AC4's tamper-evident boundary).
- **Out-of-repo, it is verifiable**: the named PR exists on the remote, was merged by a human account, and its diff contains this freeze transition. That check is cheap for a human or CI to run and impossible to forge from inside the working tree — this is the strongest evidence available **without** adding auth infrastructure (signature-grade sign-off explicitly deferred, §8).
- Interactive freezes without a PR (user says "freeze it" in-session) record `"user@session <date>"` — weaker, allowed, and *visibly* weaker in the record, which is the point.

## 4. Freeze lint (realizes S2 — anchors, not layout)

`freeze_lint.py <artifact-type> <file>` → exit 0 or a named-defect list (file + missing anchor). Per-type anchor sets, F4's accepted risk made concrete — the lint greps for **anchors, never layout**:

| Type | Anchors required to freeze |
|---|---|
| `prd` | ≥1 scenario ID (`S\d`), every scenario carries a layer tag (integration/E2E), an out-of-scope section, an unknowns section, a success-metric section |
| `design` | ≥1 `realizes S\d` reference; every PRD scenario ID appears at least once (forward coverage at *mention* level — full semantic coverage stays `cross-artifact-consistency`'s job) |
| `impl-plan` | every layer names `serves S\d`; ≥1 reversibility mention |
| `adr` | context / decision / alternatives / consequences / status anchors |

The extraction regexes are **lifted from `cross-artifact-consistency`'s frozen design** (same IDs, same tags — the PRD's §8 reuse, one level shallower). Two contract lines carved into the SKILL.md: *lint-clean is necessary, not sufficient* (review judgment + sign-off remain independent), and *the lint never gains content opinions* (the Goodhart guard from PRD §6).

## 5. `gates.json` — the registry (resolves U1: authored, matrix is checked)

**`gates.json` is hand-authored; FLOW.md's matrix is verified against it** — parse-for-verification, never parse-for-generation (a read-only, failure-tolerant parse that fails CI loudly beats a fragile generator that fails silently). Schema:

```json
{
  "version": 1,
  "phases": ["SPEC","PLAN","IMPL-PLAN","IMPL","VERIFY","PRE-PR","OPEN","COPILOT","ADDRESS","REVIEW","SHIP"],
  "gates": [
    { "skill": "prd-review",       "phases": ["SPEC"],      "blocking": true,  "freezes": "prd",
      "fires": "PRD authored or edited" },
    { "skill": "design-review",    "phases": ["PLAN"],      "blocking": true,  "freezes": "design",
      "fires": "design drafted (NEW feature)", "requires_frozen": ["prd"] },
    { "skill": "impl-plan-review", "phases": ["IMPL-PLAN"], "blocking": true,  "freezes": "impl-plan",
      "requires_frozen": ["design"] },
    { "skill": "ui-design-review", "phases": ["PLAN","IMPL"], "blocking": false,
      "fires": "feature has user-facing UI" }
  ]
}
```

- `requires_frozen` is the load-bearing field: it makes "entering IMPL — what must already be satisfied?" (S5) a query — join `requires_frozen` against `state.json` statuses.
- `fires` stays an English string **by design** — it is documentation for the agent reading the registry, not a predicate engine (no DSL; the kitchen-sink reflex rejected again).
- A phase/artifact pair with no entry returns an explicit `"no gate registered"` (S5 edge) — the tool never guesses.
- `registry_check.py` parses the matrix block in FLOW.md (skill name + ✓ columns + the side-path list) and asserts set-equality with `gates.json` membership, failing **in both directions naming the row** (S6). The matrix's footnote richness is NOT checked — prose stays prose.

## 6. Resume + reporting (realizes S1)

`state_tool.py report <feature-dir>` prints: each artifact's status (+ computed flags), the current phase (first phase whose `freezes` target is unfrozen), and the next required gate (from the registry). The S1 edge: a feature dir with artifacts but no `state.json` reports `UNMANAGED — run state_tool.py init` and **infers nothing**. `init` writes all-`draft` entries (never `frozen` — initialization cannot manufacture evidence).

The `agent-rails` SKILL.md instructs the model: **at any phase transition or session resume on a feature with a `state.json`, read it (and consult `gates.json`) before proceeding; a `requires_frozen` not satisfied is a STOP, not a nudge.** Hooks stay regex for now (resolves U5: defer hook-side registry reads — per-edit jq latency for marginal gain; the agent-facing surface + CI checks deliver the value; revisit if gate misses persist in dogfooding).

## 7. F5 — gates write state, or it rots (the carried design requirement)

Amendment sites, one line each (the freeze-performing skills gain a final step): **`prd-review`** Pass 7, **`design-review`** freeze ceremony, **`impl-plan-review`** freeze-readiness, **`adr-review`** accept step, **`architecture-design`** freeze → each ends with *"record the transition: `state_tool.py freeze <feature> <artifact> --gate <self> --signoff <evidence>`"* (which runs the lint internally — one entry point, no way to write `frozen` without passing shape). `project-bootstrap` P3 gains *"run `state_tool.py init`"*. These amendments ship in the same PR stack as the tools — shipping the file format without the writers is how status files die.

## 8. MVP cut + deferrals

**In:** the three files, three reference scripts, CI workflow, the six skill amendments (§7), dogfood `state.json` for this very feature.
**Deferred:** hook-side registry consumption (U5) · backfill of pre-rails features (PRD §4) · a cross-feature index (`state_tool.py report --all` can scan dirs later) · signature-grade sign-off (§3 boundary) · matrix *generation* from the registry.

## 9. Failure modes

- **Torn write** → atomic replace; reader treats unparseable JSON as MALFORMED, fail-closed (S3).
- **Hash mismatch from innocent reformat** → POST-FREEZE-DRIFT by design (§2); resolution is re-freeze via amendment, never lint-loosening.
- **FLOW.md matrix reformatted so the parser fails** → `registry_check.py` exits non-zero with a parse error = red CI; a parser that can't parse **fails, never passes** (fail-closed).
- **Registry says `requires_frozen: ["design"]` but the feature legitimately skipped design** (fix-shaped work) → FLOW.md's "when to skip phases" applies: state entries for skipped artifacts stay `absent`, and the SKILL.md routes skip-eligibility to FLOW.md rather than encoding it in JSON (the registry describes gates, not exemptions).
- **Agent deletes `state.json`** → `cross-artifact-consistency` gains one check: a feature dir with review docs but no state file is flagged UNMANAGED (its defect taxonomy already extended by S4's two flags).

## 10. Attack surface (threat-model lite — no external input, no privilege)

All inputs are repo-local files; the scripts make no network calls and run with the agent's existing permissions. The two real threats are *self-inflicted*: **forged sign-off** (§3 — fabricatable in-repo, verifiable out-of-repo, boundary stated) and **stub-content lint-gaming** (PRD §6 Goodhart guard — review remains the other half). DoS/spoofing/info-disclosure: N/A (no service, no secrets in state — statuses and hashes only).

---

## Freeze marker

*Not yet frozen.* Awaiting `design-review` (beside this file) + user sign-off. Impl-plan may not begin until then.
