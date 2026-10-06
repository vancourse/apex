# How jarvis was built with agents: 458 sessions, 2026-07-03 to 2026-10-06

## Headline

- **Scale.** There were 458 sessions: 368 interactive and 90 scheduled. They contain 6,268 operator messages, 123,071 Bash calls, 20,125 Edits, 9,938 Writes, 323 context compactions and 162 interrupts. That is about 20 Bash calls for every operator message.
- **Where the operator's messages go.** One in three is ceremony: approve, push, open the PR, merge. One in five corrects something. One in seven asks for new work.
- **What the operator catches is rarely code.** The biggest classes are:
  - something other than what was asked was built or designed (170)
  - work was called done but the real screen disagreed (111)
  - domain facts were wrong (102)
  - a screen did not match the design (97)
  - the agent stopped or asked when it could have acted (88)
- **The agent's own corrections are mostly retractions.** 77% of 645 were wrong statements, not wrong code. 75% had already reached the operator, a PR or issue, or another session before the agent caught them.
- **Rules did not stop repeats.** 37% of operator corrections (346 of 930) were covered by a rule that was already written down in CLAUDE.md or memory.

## Does this show every mistake caught while working?

No. It shows mistakes that someone said out loud, plus hook blocks. Mistakes the agent fixed without comment appear only as totals.

| Lens | What it contains | What it misses |
|---|---|---|
| Operator-caught | 5,398 labelled operator messages, with 930 to 997 tagged with a mistake class | Mistakes nobody noticed. About 1,096 rows (20%) are duplicates in the logs, so counts are inflated |
| Agent self-corrections | 645 classified admissions, matched by phrases like "I was wrong" from 720 snippets. 119 of them were actually prompted by the operator | Anything fixed silently. Snippets replay about 1.5x across resumed transcripts |
| Hook blocks | 271 records | 45 records are not hooks at all, and 35 are hooks whose script was missing |
| Silent catches | Counts only: 4,569 red test runs, 8,899 tool errors, 209 denied permissions | What was wrong in each one |

Who caught a mistake, and whether it had already reached the operator, were inferred from snippets of about 700 characters. So the operator-caught share is a lower bound.

## 1. Where the operator's messages go

These are the 5,398 labelled messages. Before labelling, 339 bare approvals and 531 messages under 15 characters were skipped.

| Bucket | Intents | Messages | Share |
|---|---|---|---|
| Ceremony | approve or go 1,071 + git and PR operations 720 | 1,791 | 33% |
| Direction | new work 802 + context 330 + scope redirects 132 | 1,264 | 23% |
| Correction family | corrections 577 + repeats 365 + frustration 208 | 1,150 | 21% |
| Questions to the agent | 881 | 881 | 16% |
| Harness admin and other | 230 + 82 | 312 | 6% |

- **Ceremony outnumbers new-work requests 2.2 to 1** (1,791 against 802). Adding back the 339 skipped bare approvals gives 2,130 of 5,737 (37%). The 531 very short messages are mostly the same "yes" or "go" shape, so the real share is probably close to 40%.
- **Corrections outnumber new-work requests 1.4 to 1** (1,150 against 802).
- **The repeat count is inflated.** In Aug 31 to Sep 7, 204 duplicate rows were labelled as repeats. Without them, ceremony is 34% and the correction family is 18%.

| Period | Distinct messages per day (est.) | Ceremony | New work | Correction family | Questions | What dominated |
|---|---|---|---|---|---|---|
| Jul 3 to Aug 1 | 19 | 30% | 28% | 17% | 14% | Duplicate components, household data in git, design churn |
| Aug 1 to 7 | 108 | 42% | 13% | 18% | 17% | Push-consent loop, bare decision questions, extraction direction misread |
| Aug 7 to 11 | 153 | **49%** | 8% | 9% | 10% | CI and docs-render-train crisis ("lost 2 full days") |
| Aug 11 to 16 | 115 | 26% | 16% | 17% | 16% | Tests green but product broken, one-PR rule restated 7 times, secrets drip-fed |
| Aug 16 to 31 | 37 | 29% | 13% | **29%** | 18% | Stopping early (41 of 148 unique corrections), retired path resurfacing |
| Aug 31 to Sep 7 (distinct basis) | 58 | 37% | 19% | 19% | 17% | Done-claims failing on dev-jarvis, single-PR rule restated 6 times |
| Sep 7 to 12 | 96 | 33% | 17% | 17% | 21% | UI fidelity; the assistant bypassed the semantic model |
| Sep 13 to Oct 6 | 20 | 33% | 11% | 19% | **23%** | Wrong domain data (43 of 131 mistake rows) |

- **Ceremony never fell below 26% in any period.** It peaked at 49% in Aug 7 to 11, when the push-consent gate made the operator type or approve each push. Rules saying "arm auto-merge, never ask" were restated in at least four periods, and the share did not move.
- **New-work share peaked in July at 28%** and ran between 8% and 19% after that.
- **Questions rose to 21 to 23% in the last two periods.** They are mostly "what does this term mean", "did you refresh", and "I thought we had ...". The operator's picture of what was built drifted from what shipped.
- **The mix of mistakes shifted.**
  - July and August corrections are about process and architecture: duplicate components, CI machinery, PR granularity, and designing without building.
  - September and October corrections are about product truth. UI fidelity is about 30% of distinct corrections in Sep 7 to 12. Domain data is 43 of 131 mistake rows (33%) in Sep 13 to Oct 6.
- **Rule coverage fell with that shift.** 42 of 58 corrections (72%) had a rule in Aug 31 to Sep 7, 13 of 80 (16%) in Sep 7 to 12, and 32 of 110 (29%) in Sep 13 to Oct 6. Process mistakes can be written down as rules. Wrong domain facts cannot.

## 2. What the agent gets wrong that only the operator catches (ranked)

These come from 997 mistake labels, 169 of them "other". Counts include duplicate log rows, so they are inflated by roughly 20%.

1. **Built or designed something other than what was asked: 170** (misread intent 95 + built the wrong thing 75).
   - The extraction direction was restated about 20 times over Aug 1 to 7, and about a dozen more times in Aug 11 to 16.
   - The parser and vision lanes were built in series although the design said parallel.
   - The assistant was locked to answers-only.
   - Categories were derived at read time; the operator wanted them stored at write time.
   - The operator said: "I spent a couple of days making the design perfect.. and you didnt implement it" and "WAIT, the goal is NOT to create dedicated parsers."
2. **Called done, but the real surface disagreed: 111** (claimed done without checking 75 + checked only on a fixture 36).
   - The same extraction classification failure came back on Aug 16, 18 and 19. Each fix was green on a canned-engine harness.
   - The operator said: "when you tested it, you thought it was all working whereas when I tested it, it didnt work"
3. **Wrong domain data: 102.** This is the largest class in the last period (43 of 131).
   - Examples: what counts as a trip or a subscription, currency dropped silently, card payments confused with credit-line payments.
   - The operator said: "If I havent asked you to ignore USD, why did you build it so that USD is ignored?" and "we seem to be finding a lot of issues withing the first 5 minutes of my really using Purser"
4. **A screen did not match the design, or could not be understood: 97.**
   - Examples: elements from the supplied artwork missing, dead buttons, no way back from a sub-page, jargon with nothing explaining what to do.
   - The operator said: "Are you yet to get to it or you didnt see that in the artwork that i gave you."
5. **Stopped early, or asked when it could act: 88.** This was the largest class in Aug 16 to 31 (41 of 148 unique corrections).
   - Examples: handing the operator commands to run, citing the one-front posture or a blocker, asking for keys that were already in the vault.
   - The operator said: "I explicitrly asked you to keep going, right" and "you are hiding behind excuses that some or the other prior part of the implementaiton is blocking you"
6. **Unsupported or stale claims: 52** caught by the operator. The agent's own retractions add 251 more claim errors.
   - Examples: "no microVM on this box", "model key missing", "no GitHub App exists", and memory notes repeated as fact.
   - The operator said: "are there other numbers you claimed that you never measured?"
7. **Slow or inefficient: 52.** Mostly full-suite runs and finding missing settings one per round trip.
   - The operator said: "for ONE LINE change, you took 30 minutes in unnecessary testing"
8. **Git and CI mishandled: 50.** PRs opened per issue, CI not watched after auto-merge was armed, household data committed.
   - The operator said: "DO NOT OPEN PRs for each issue - use commits." and "How come you were not monitoring it."
9. **Ignored an existing component, or rebuilt a path that had been retired: 44.**
   - The operator said: "instead of enhancing or leveraging what i already built, claude code keeps building duplicate surfaces/components" and "we wanted to completely delete this path. Not sure why its still there.."
10. **Over-engineered, or added process: 36.** CI and docs-render machinery, and 40 commits of design docs before any code.
    - The operator said: "I have lost atleast 2 FULL DAYS of productivity" and "Well, I aalready have too many hooks and gates.. they are not very effective."

Smaller classes: wrong location or worktree 12 (clustered from July to early August), scope creep 12, prose instead of working code 2.

## 3. Mistakes repeated although a rule already existed

- **Coverage.** 346 of 930 coverage-labelled corrections (37%) already had a covering rule in CLAUDE.md or memory. 451 (48%) had none, and 133 are unknown. Of the corrections where coverage could be judged, 43% had a rule.
- **Two caveats.**
  - In Aug 1 to 7, many "yes" rules were written after the incident they cover. Rules follow corrections.
  - In Aug 16 to 31, several "no" labels are cases where a posture rule (one active front, the one-issue cap) gave the agent a reason to stop, and the operator overrode it.

| Instruction | How often it was restated | Rule on file |
|---|---|---|
| One PR per line of work, one commit per issue | At least 25 times in 6 of 8 periods: 7 in Aug 11 to 16, 6 across 5 sessions in Aug 31 to Sep 7, hand-prefixed onto 5 lane prompts in Aug 7 to 11 | Memory entry already says "said 3 times" |
| Work autonomously, don't stop, don't wait for the word | About 50 times in 7 periods, at least 12 in Aug 16 to 31 | Memory and CLAUDE.md |
| Give the problem, options and a recommendation | At least 18 times in 5 periods | CLAUDE.md: never hand the operator a bare question |
| Don't ask to merge; arm auto-squash | At least 20 times: 11 "merge it" in July, 7 in Aug 7 to 11, 3 in Aug 11 to 16 | Memory |
| No full suite per commit or locally | About 15 times in 5 periods, 3 of them in one session | Memory |
| Drive the real screen before saying it works | 8 of 14 cases in Aug 11 to 16 had the rule; 23 cases in Aug 16 to 31 | Memory |
| The retired enrollment path stays dead | It came back in 4 periods, from Aug 11 to October | Memory |
| No household data in git | About 10 checks in July; data reached master again by October | Memory plus the scanner |

**The agent's side shows the same thing.** Stored lessons went unapplied in at least 6 sessions:
- A piped `tail` hid a failing exit code twice, once with the agent noting it knew better.
- Negative claims from a narrow search happened in about 8 sessions despite "ls before designing".
- Stale git state was read as current in about 6 sessions.

**What this says about prose rules:**
- **Prose loses at moments no hook intercepts:** the end of a turn (stop and ask), creating a PR, and the sentence that claims something. These are exactly the most-repeated items.
- **Where a mechanism exists, the class shrinks.** Wrong-location mistakes are 12 in total and cluster in July to early August. Later, the worktree-isolation hook logged 12 blocks (6 unique) of edits aimed at the wrong checkout. That is consistent with the hook doing the job, though not proof.
- **The rules conflict, and the agent takes the reading that lets it stop.**
  - "Never push without asking" against "don't wait for my go-ahead".
  - "Arm auto-merge, never poll" against "how come you were not monitoring it".
  - "One active front" against "do all of that work".

  The ceremony (1,791) and stopping (88) totals are where these conflicts land.
- **Writing a rule moves the gap; it does not close it.** After Aug 31 the repeat label fell below 10 per period, but the same instructions kept being given and were labelled as corrections instead.
- **A rule can be wrong and still be obeyed.** In Sep 7 to 12, the CLAUDE.md text in context steered sessions away from the query layer the operator wanted. It was amended the next day.
- **Chat corrections do not last.** There were 323 compactions across 458 sessions, so a correction given in chat survives at most until the next compaction.

## 4. What gets caught without the operator

### Agent self-corrections (645)

| What was wrong | Count | Share |
|---|---|---|
| A claim or report | 251 | 39% |
| A diagnosis | 153 | 24% |
| A plan or design | 94 | 15% |
| Environment or tooling | 58 | 9% |
| A code bug | 40 | 6% |
| Data or domain | 31 | 5% |
| A test or fixture | 18 | 3% |

| How it was caught | Count | Share |
|---|---|---|
| Re-reading the primary artifact (DDL, workflow file, git ref, a replayed run) | 301 | 47% |
| Prompted by the operator | 119 | 18% |
| Re-reading its own work | 92 | 14% |
| Running tests | 69 | 11% |
| A CI result | 25 | 4% |
| A tool error | 10 | 2% |
| **Looking at the UI in a browser** | **4** | **0.6%** |
| **A hook** | **3** | **0.5%** |

- **Most were already out.** 487 of 645 (75%) had reached the operator, a PR or issue, or another session before the catch. By type:
  - 87% of claim errors and 86% of diagnoses had already reached someone.
  - Only 30% of code bugs and 38% of environment slips had.

  Tests and CI protect code. Nothing protects statements.
- **Some "self-corrections" were the operator's work.** 119 (18%) were prompted by the operator, so 526 were genuinely self-initiated.
- **The agent almost never looks at the screen.** Only 4 self-corrections came from a UI check, against about 208 operator catches of done-claims and screen mismatches.
- **Silent catches dwarf all of this:** 4,569 red test runs, 8,899 tool errors and 209 denials. They are why code bugs are only 6% of the agent's admissions. Review effort still goes to code: 157 python-review skill invocations.
- **Recurring families with no mechanism behind them:**
  - negative claims from a narrow search (about 8 sessions)
  - stale or wrongly scoped git state read as current (about 6 sessions)
  - probes without the tenant setting reading zero rows as "empty" (4 sessions)
  - "tool, key or vault absent" probed in the wrong place, such as Windows instead of WSL or a container instead of the host (about 6 times in 5 sessions)
  - conclusions inherited from stale memory notes or issue bodies (7)
  - probes that are not the app's own instrument (about 12)
- **Other agents are the strongest check on statements.**
  - In 5 sessions another session overturned a diagnosis that had already been broadcast.
  - Adversarial review passes caught about 8 design errors the cooperative pass missed.
  - The most serious find came from a self-audit: an exact-match scan reversed an earlier all-clear and found real statement descriptors already on master.
- **Self-inflicted damage from shared state:**
  - releasing claims from the main checkout dropped other sessions' claims in 3 sessions, one of them losing 26
  - a WSL shutdown took down both the dev and prod fleets
  - a destructive migration on a real store lost hundreds of rows
  - two PRs merged 49 seconds apart left master red

### Hooks

Of the 271 block records:
- 45 are not hooks at all.
- 35 are broken hooks: the script was missing in a worktree, so Python exited 2 and blocked every Bash call. One session hit this 17 times.
- 191 are real evaluations.

Across all 271, verdicts were: **prevented a real mistake 40 (15%)**, mixed 90 (33%), friction or false positive 141 (52%). Hooks caused 3 of 645 self-corrections: they stop actions, they do not correct beliefs.

**Hooks that earn their keep:**

| Hook | Records (unique) | What it stopped |
|---|---|---|
| Pre-commit money-figure scanner | 9 (6), plus 4 earlier on synthetic fixtures | Real figures in an ADR, code and tests. It does not cover issue bodies, subagent prompts or files outside git |
| Worktree-isolation Edit hook | 12 (6) | Edits aimed at the base checkout or another session's worktree |
| Env-values dump gate | 9 (7) | Env dumps, after two earlier key leaks |
| `--no-verify` guard | 4, plus 1 earlier | Attempts to skip the scanner on merge and wip commits |
| Merged-PR push gate | 2 (1) | A push onto a branch whose PR had already merged |
| Rewritten-history pre-push refusal | 1 | Republishing about 2,100 pre-rewrite commits containing scrubbed household data |
| Stash hook, GitHub branch protection, preview port guard | 1 each | A shared stash, a direct push to master, a port held by another session |

**Hooks that cost without protecting:**
- `reset --hard` to a remote ref: 40 records, all routine worktree re-cuts. It is also leaky: a reset behind `|| true` ran unblocked in another session.
- Missing-script hooks: 35 blocks.
- "Force push to master": 22 records, firing on feature-branch pushes and PR-create flags. At most 1 was plausible.
- The secrets-on-edit scanner: 3 records, all fake fixture keys.

**Mixed:**
- `pipe_mask`: 37 records (29 unique, 8 sessions). It targets a proven class of false greens but also blocked `gh issue create` and `git commit`.
- `.env` rules: 25 records. About 6 were real credential-file edits; the rest were read-only greps and backups.
- Claim collisions: 7.
- Secret-file touch gate: 7, mostly blocking names-only presence checks.
- The push-consent gate: the agent could set the operator-only variable itself, so it is a reminder, not a barrier.

**The pattern:** the hooks that work each cite a measured incident and guard something irreversible, such as data leaving the box, a shared ref, or another session's tree. The ones that cost match command text rather than meaning, and fail closed when their own script is missing.

## 5. What the operator does by hand that a mechanism should do

| Manual job | Evidence | Mechanism |
|---|---|---|
| Approving each push, PR and merge | 1,791 ceremony messages plus 339 bare approvals; about 29 bare "push it and open the PR" in Sep 7 to 12; about 15 hand-typed pushes in Aug 1 to 7 | Default to push, open PR and arm auto-squash after the local gate; the operator's only word is "hold" |
| Watching CI after arming auto-merge | About 12 operator reports of red in Aug 16 to 31 alone | A PR monitor bound when the PR opens, waking the session on red or a conflict |
| End-to-end testing on the real screen | 208 operator catches against 4 agent UI checks | A scripted walk on the named target, attached to every "done" |
| Checking deploy state | "did you refresh 9999" 5 times; about 24 redeploy requests in September | A post-merge step that redeploys and reports target, SHA and time |
| Relaying between sessions | About 40 pasted card prompts in July; 50 relays plus 34 lane dispatches in Aug 7 to 11; one message sent to 7 sessions in 20 minutes | A coordinator and session registry |
| Spotting duplicate work | Several sessions fixing the same red master in two periods; the operator asked for "a hook that checks open PRs before building" | A mechanized claim and open-PR check before the first edit |
| Re-adding standing rules to every prompt | 5 lane prompts hand-prefixed in Aug 7 to 11 | A prompt generator that emits the standing contract |
| Supplying domain ground truth | 102 data and domain corrections | A ground-truth file plus golden checks |
| Running the agent's commands in his own shell | Bash syntax in PowerShell 5.1, a missing `cd`, MSYS path mangling, placeholders; in 5 of 8 periods | The agent runs it, or tests the command in the operator's shell first |
| Feeding secrets one round trip at a time | 9 rounds for one sync; keys requested that were already in the vault | Enumerate every required name against the vault and env in one pass |
| Auditing for data leaks | About 10 "is any real data in the repo" checks in July; another cleanup in October | Extend the scanner to issue bodies, PR bodies and subagent prompts |
| Translating jargon | 881 questions (16%), rising to 21 to 23% | Enforce a plain-language decision brief |

## 6. Implications for the process design

- **Invert the ceremony default.** Once the local gate passes, the agent pushes, opens one PR per line of work and arms auto-squash; the operator only says "hold". Ceremony is 1,791 of 5,398 messages (33%), 2.2 times the new-work requests, and never below 26% in any period.
- **Make "done" an artifact, not a sentence.** It needs a walk on the operator's named target with the SHA and a screenshot or walk log. 208 operator catches were done-claims or screen mismatches, and only 4 of 645 self-corrections came from looking at a screen.
- **Capture ground truth before building money, trip or currency logic.** Keep the household invariants and known values in a git-excluded file, check them with golden tests, and list every silent default in the PR. Domain errors are 102 corrections and 33% of the last period's mistakes, where only 29% of corrections had any rule.
- **Read intent back before the first commit.** State what is being built, what is not, which paths are retired, which file is the screen of record, and the operator's acceptance tests as done criteria. Misread intent plus building the wrong thing is the largest class (170).
- **Require receipts for statements.** Claims that something exists, is absent, is deployed or caused a failure must cite what was read this turn, and a where-is helper should search code, docs, branches, issues and vault names. 77% of self-corrections were wrong statements, and 87% of claim errors reached the operator against 30% of code bugs.
- **Gate the end of a turn.** Block an offer-shaped ending ("want me to", "say the word") while the work list still has open items. There were 88 stopped-early corrections and about 50 restatements of "work autonomously".
- **Mechanize the five most-repeated rules and delete their prose:**
  - one PR per line of work (25 or more restatements)
  - arm and watch CI (20 or more)
  - problem, options and a recommendation (18 or more)
  - no local full suite (about 15)
  - retired paths stay dead (back in 4 periods)

  37% of corrections already had a rule.
- **Resolve the conflicting rules in one place:** push consent against autonomy, arm-and-stop against watching CI, one front against finishing everything. Each conflict let the agent take the reading that stops work.
- **Prune the hooks.** Keep the roughly 9 that prevented real harm, fail open when a script is missing, and match meaning rather than text. Only 40 of 271 records (15%) prevented a real mistake; 141 (52%) were friction or noise.
- **Replace the operator as message bus with a coordinator.** There were about 124 relay or dispatch messages in two periods, and duplicate fixes of the same red master in two periods.
- **Extend the household-data boundary beyond commits.** The scanner made 9 real blocks, but figures still reached an issue body and code comments, and statement descriptors reached master.
- **Fix the measurement before the next analysis.** 20% of operator rows (about 1,096) are duplicates, self-correction snippets replay about 1.5x, and the 4,569 red test runs and 8,899 tool errors carry no recorded cause.
