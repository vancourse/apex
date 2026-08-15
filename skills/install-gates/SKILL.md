---
name: install-gates
description: Install the blocking half of apex's PR discipline into a target repo — a Claude Code plugin ships skills and hooks, it cannot ship CI, so the layer that binds everyone has to be scaffolded in rather than installed. Produces two vendored gates under the repo's `ci/` (pr_body_check.py, which derives a PR's required sections from its own diff; pre_pr_check.py, which runs CI's own commands locally plus three pure-git preflights — a branch cut from a rewritten base, a docs-only branch carrying source, and a branch that merged the default branch and then deleted files it brought in), a pull_request CI job wired to block the merge, and a `[tool.apex]` block naming the repo's custody paths. Fires when a repo adopts apex and wants teeth rather than advice, when PR bodies keep landing empty because `gh pr create --body-file` skips the web-UI-only template, or when a branch merges green while carrying a second edition of someone else's already-merged commit. Pairs with apex:detect-stack (upstream — names the CI host the job is written for), apex:pr-discipline (upstream — the rules these gates make binding), apex:cicd-review (downstream — audits the workflow job this writes), and apex:pr-review-primer (the body shape pr_body_check.py enforces). Keywords: install gates, CI gate, blocking check, required status check, PR body check, pre-PR check, branch protection, pull_request_template, scaffold CI, squash-merge base, body-file.
---

# Install Gates

apex's hooks fire inside Claude Code sessions and nowhere else. GitHub applies `.github/pull_request_template.md` **only in its web UI** — `gh pr create --body-file` skips it entirely, and so does every agent and every CLI user. So a repo can install apex, follow every skill, and still merge a PR whose body is empty and whose branch was cut from a base the default branch has since rewritten. **A plugin cannot ship CI. It can ship the files and the wiring, and that is exactly what this skill does** — it carries the blocking half into a target repo and tells you plainly which tier each piece lands in.

## The enforcement split

State this to the user before you install anything. The most expensive misunderstanding about apex is assuming that installing the plugin gave the repo teeth.

| Layer                                | Binds                                                     | Ships with apex                              |
| ------------------------------------ | --------------------------------------------------------- | -------------------------------------------- |
| Session hooks (`hooks/*`)            | Claude Code sessions only — advisory, fail-open            | **Yes, natively** — installed with the plugin |
| Local `pre_pr_check.py`              | Only when the developer runs it                            | **As a file this skill installs**             |
| CI job running `pr_body_check.py`    | Everyone who opens a PR — blocks the merge                 | **Only as scaffolding this skill wires**      |

Three rows, three different populations. A hook that fires for you does not fire for the teammate who never opens Claude Code. A script on disk does not fire for the branch that never runs it. Only the bottom row binds everyone, and only the bottom row is the one apex cannot hand you finished.

## When to invoke

- A repo **adopts apex** and wants enforcement rather than advice — usually right after `apex:project-bootstrap` or the first `apex:detect-stack` pass.
- PR bodies keep **landing empty or template-shaped**. The tell is a repo with a `pull_request_template.md` that most PRs visibly ignore: those PRs were filed from the CLI or by an agent, where the template does not exist.
- A branch merged clean and **relanded work that was already on the default branch**. Nothing was broken, the forge reported it mergeable, tests passed — it just shipped two editions of somebody else's change. That is the `base` preflight's exact failure mode, and it costs a revert plus a re-review to undo.
- A branch merged clean and **deleted work that was already on the default branch** — the same root cause seen from the other side. A replay built from the wrong base dropped four files another PR had just added; the apply was clean, the PR reported mergeable, the suite was green. That is the `replay` preflight's failure mode, and it costs whatever the deleted work cost, paid twice.
- The repo is about to **turn on branch protection** and needs at least one required check with real content in it.

**Skip** for a repo with no CI at all and no intent to add any — install `pre_pr_check.py` alone, and say out loud that it binds nobody but the person who runs it.

## Method

### Step 1 — Name the CI host before writing a line of YAML

Read, in order, and stop at the first hit:

1. `apex.profile.toml` at the repo root — if `apex:detect-stack` has already run, the CI host is recorded there. Do not re-run a full detect-stack pass just for this; reading one field is cheaper than a whole probe cycle.
2. `.github/workflows/*.y*ml` → GitHub Actions. `.gitlab-ci.yml` → GitLab CI. `.circleci/config.yml` → CircleCI. `Jenkinsfile` → Jenkins. `azure-pipelines.yml` → Azure Pipelines.
3. Nothing at all → ask. A repo with no CI is a real answer, not a detection failure, and it changes the recommendation (Step 3's fallback).

**Conflicting signals — a GitHub remote plus a `.gitlab-ci.yml` — mean you ask, not pick.** Writing a GitHub Actions job into a repo whose pipelines run on GitLab produces a file that never executes, and a repo that believes it is guarded is worse off than one that knows it is not.

Also record the repo's Python situation: `pr_body_check.py` needs **Python 3.11+** for `tomllib`. On an older interpreter it degrades to an empty sensitive-path config rather than crashing, but Step 4 then does nothing.

### Step 2 — Copy the two gates in

Copy from the plugin's [`templates/gates/`](../../templates/gates/) into the target repo. `ci/` is the suggested home — both scripts resolve the repo root through `git rev-parse --show-toplevel` and fall back to their parent directory, so any depth works, but `ci/` is what every example here assumes:

```
templates/gates/pr_body_check.py             ->  ci/pr_body_check.py
templates/gates/pre_pr_check.py              ->  ci/pre_pr_check.py
templates/gates/acceptance_check.py          ->  ci/acceptance_check.py
templates/gates/milestone_completion_gate.py ->  ci/milestone_completion_gate.py
templates/gates/tests/                       ->  ci/tests/            (optional, recommended)
```

Copy the tests too unless the user declines. They cost one directory and they are the only thing standing between a live gate and a **silently dead** one: a check that stopped reading git, or lost an import in a refactor, looks exactly like a check with nothing to report. The suite drives both scripts against real temporary repositories precisely because the predicate tests cannot prove the gate is wired to anything.

If the repo has no PR template yet, install [`templates/github/pull_request_template.md`](../../templates/github/pull_request_template.md) at the same time. `pr_body_check.py` compares each section against the template's own placeholder text, so **without a template the placeholder rule cannot fire** and pasting the skeleton back would count as an answer.

### Step 3 — Wire the blocking job

**GitHub Actions — complete and copy-pasteable.** Write this to `.github/workflows/pr-gates.yml`:

```yaml
name: pr-gates

on:
  pull_request:
    # `edited` is load-bearing. Without it, fixing the body does not re-run the
    # check, so the PR stays red until an unrelated push happens to clear it —
    # and a gate you cannot clear by doing the right thing is a gate people
    # learn to bypass.
    types: [opened, edited, reopened, synchronize, ready_for_review]

permissions:
  contents: read

jobs:
  pr-body:
    name: pr-body
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # The base commit must be in the local object store for the diff below.
          # At the default depth of 1 it is not, and the diff silently sees the
          # whole branch as new.
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11" # tomllib, which the sensitive-path config needs

      - name: PR body carries what its diff calls for
        env:
          # Never interpolate ${{ github.event.pull_request.body }} directly into
          # a `run:` block. It is attacker-controlled text and would be pasted
          # straight into the shell. Through `env:` it is data, not script.
          PR_BODY: ${{ github.event.pull_request.body }}
          PR_AUTHOR_TYPE: ${{ github.event.pull_request.user.type }}
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
        run: |
          git diff --name-status "$BASE_SHA...$HEAD_SHA" \
            | python ci/pr_body_check.py
```

`PR_AUTHOR_TYPE` is what exempts bots — a dependency bot cannot write a reuse verdict, and blocking its lockfile bump helps nobody.

**Add the acceptance step to the same job** when the repo works in issues and milestones (`apex:release-loop`). It needs a token, because it reads the issues the body closes:

```yaml
      - name: PR answers the acceptance criteria of the issues it closes
        env:
          PR_BODY: ${{ github.event.pull_request.body }}
          GH_TOKEN: ${{ github.token }}
        run: python ci/acceptance_check.py
```

### Step 3b — Wire the completion gate on a **scheduled** lane

This one cannot go in `pr-gates.yml`, and the reason is not stylistic. The condition it watches — a milestone whose issues are all closed, still sitting open — becomes true *after* the final PR merges, which is exactly when no PR lane is running. Put it on a schedule, in its own workflow or as a scheduled job in an existing one:

```yaml
on:
  schedule:
    - cron: "0 9 * * 1-5"

jobs:
  milestones:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Finished milestones are closed (gate)
        if: ${{ github.event_name == 'schedule' }}
        env:
          GH_TOKEN: ${{ github.token }}
        run: python ci/milestone_completion_gate.py
```

**This is CI wiring, not plugin wiring** — apex ships the script and this snippet, and the consuming repo adds the step. A plugin cannot install CI, which is the premise of this whole skill. Do **not** add the completion gate to branch protection: it is a scheduled report about the tracker, not a verdict on any PR, and requiring it would block every merge on the state of an unrelated milestone.

The measurement behind it: one repo's first 33 days ended at **47 milestones open, 0 closed, 11 of them holding zero open issues**. Nothing was broken and every issue had closed correctly — there was simply no moment that said "this release is done".

**GitLab CI — the same contract in its dialect:**

```yaml
pr-body:
  stage: test
  image: python:3.11
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  variables:
    PR_BODY: $CI_MERGE_REQUEST_DESCRIPTION
  script:
    - git fetch --depth=0 origin "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME"
    - git diff --name-status "origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME...HEAD"
      | python ci/pr_body_check.py
```

GitLab's equivalent of a required check is **merge-request pipelines plus "Pipelines must succeed"** in the project's merge-request settings. Wire that or the job is decorative.

**Any other CI system — explain the contract, do not guess the dialect.** The script's whole interface is four things:

| Surface        | Contract                                                                                                     |
| -------------- | ------------------------------------------------------------------------------------------------------------ |
| stdin          | `git diff --name-status <base>...<head>` — the merge-base form, three dots                                    |
| `PR_BODY`      | the PR/MR description, passed as an environment variable, never interpolated into a shell string               |
| `PR_AUTHOR_TYPE` | `Bot` exempts the author; anything else (or unset) is checked                                                |
| exit code      | `0` pass, `1` fail; findings print as GitHub `::error::` annotations, which are harmless plain text elsewhere |

Hand the user that table and let them write the job for a system they can actually verify. **A job written from a guessed dialect that never runs is worse than no job**, because the repo now believes it is guarded.

### Step 4 — Declare the repo's custody paths

`pr_body_check.py` adds a **Risk note** requirement when the diff touches a trust or custody path. Which trees those are is a per-repository fact, so the script reads them instead of shipping a guess. Add a `[tool.apex]` table to `pyproject.toml`, or — for a repo with no `pyproject.toml` — a `.apex.toml` at the root with the same keys and no table header:

```toml
[tool.apex]
sensitive_path_prefixes = [
  "services/auth/",     # decides who you are
  "services/billing/",  # moves money
  "libs/crypto/",       # signs, seals, verifies
  "deploy/",            # changes what runs in production
  ".github/workflows/", # changes what CI itself is allowed to do
]
sensitive_path_substrings = ["migration", "credential", "webauthn"]
```

Prefixes match the **start** of a repo-relative path. Substrings match **anywhere** in it, case-insensitively, which is how a `migrations/` directory buried three levels down still counts. Enumerate rather than pattern-match: the list is then reviewable in a diff, and a new sensitive area becomes a deliberate addition rather than an accident of regex.

**The selection heuristic, in one line:** a tree belongs on this list if a wrong change to it is discovered by an *incident* rather than by a *test*.

**If nothing is configured, the Risk-note rule never fires, and that is correct.** The other three rules still apply. A gate that guessed which trees are sensitive would fire on correct work in a repo it knows nothing about — and one false positive teaches the author to reach for `gh pr merge --admin`, which skips every other required check too. Silence beats a guess here. Say this to the user explicitly rather than letting them discover an inert rule six weeks later.

### Step 5 — Reconcile `pre_pr_check.py` against the jobs it mirrors

Open the copied `ci/pre_pr_check.py` and read `build_steps()` against the CI workflow, line by line. **The steps must be the same argv the CI jobs run.** If the local file says `ruff check src/` while the workflow says `ruff check .`, then "pre-PR passed" and "CI passed" have quietly become two definitions of green, and the local run is worse than nothing — it is a green light that means something else.

The shipped `build_steps()` builds each step only when the repo shows the config that job reads (`[tool.ruff]`, `uv.lock`, `[tool.pyright]`, and so on), so an unedited copy is conservative rather than wrong. There are two constants above it to set:

- `TEST_ENV` — the environment variable the suite needs before it can pass (a database URL, a service token). A step that would fail for a missing local dependency reports `SKIPPED` with the reason instead, because a red run the developer cannot act on teaches them to stop running the tool.
- `TEST_SELECTOR` — the path to a script that maps changed files to test paths, if the repo's CI narrows its suite that way. Absent, the full suite runs.

Then tell the user what the three preflights buy, because they are the part most likely to be dismissed as ceremony:

- **base** — a commit whose subject ends in `(#123)` was written by the forge's squash-merge, never by hand, so it belongs to the default branch's history by construction. One sitting in `origin/<default>..HEAD` means the branch was cut from a base the default branch has since **rewritten**. Nothing about this is broken, which is exactly why it is invisible: the merge is legitimate, the forge reports it mergeable, the tests pass. It just lands two editions of someone else's change, and the second edition is the one nobody reviewed.
- **scope** — the declaration is the conventional-commit type the author already wrote, so there is no second field to keep in sync and nothing new to forget. If every commit on the branch is `docs(...)`, the diff has to be prose; source files in it mean the branch picked up something it did not mean to. An unlabelled commit **widens** the allowed scope rather than narrowing it — the check fires on a broken promise, never on a missing one.
- **replay** — files the default branch still has, that this branch **merged in and then lost**. That is the branch reverting somebody else's merged work, and it is what a replay built from the wrong base produces: reverse-hunks for files the author never looked at, applied cleanly by `git apply --3way`, landing as ordinary deletion commits. One branch dropped **four files another PR had just added** exactly that way — clean apply, mergeable PR, green suite. It stays off branches that are merely *behind* by requiring both that the commit which added the file is already in this branch's history **and** that it arrived through a merge rather than through the history the branch was cut from. See `dropped_from_base`, which also states the rebase case it does not claim to cover.

The first two are things CI genuinely **cannot** see. The third is one it *can* — the deletions are right there in the diff — and that is exactly why it gets missed: a deletion inside your own PR reads as part of your change, and nothing draws a reviewer's eye to the four lines that are somebody else's.

All three are pure git, they cost milliseconds, and they run before anything that costs money. If a branch is cut from the wrong base, every gate below the preflight is describing a tree that is not the one that would land — so a failed preflight aborts the run rather than accumulating findings about the wrong code.

Add the run to the repo's contributing docs and to the PR template's checklist, as one line: `python ci/pre_pr_check.py` passes locally.

### Step 6 — Make it required, then prove both halves

1. **Add the job to branch protection** as a required status check (GitHub: Settings → Branches → the default branch's rule → *Require status checks to pass* → `pr-body`). A job no rule requires is decorative — the exact defect class these gates exist to catch, applied to the gates themselves.
2. **Prove the failing half.** Open a throwaway draft PR that changes one source file, with a body containing only `## What this does`. The job must exit 1 and annotate the missing `Test plan` and `Wiring`.
3. **Prove the passing half.** Fill the body in. The job must go green **on the `edited` event alone**, with no new push. If it does not, `types:` is wrong.
4. Run `python ci/pre_pr_check.py --skip-tests` on a real branch and confirm all three preflights report `PASS`, then run `pytest ci/tests` if you copied the suite.

A gate that has only ever been observed passing has not been observed at all. Both halves, or the install is not finished.

## The honest ceiling

Say this in your own words to the user, and do not soften it:

- **`pre_pr_check.py` runs when the developer runs it. A branch that never sees it is unguarded.** Documentation does not change that, a checklist item does not change that, and a hook does not change that for anyone outside a Claude Code session. It is a fast local convenience, not enforcement.
- **Only the CI job binds everyone.** That is the reason Step 3 exists and the reason Step 6 makes it required.
- **Even the CI job yields to `gh pr merge --admin`**, which bypasses every required check at once. Repository admins can always override branch protection; that is the forge's model, not a hole in these scripts. What the gate removes is the *silent* path — skipping the template now takes a deliberate, logged act rather than a `--body-file` nobody notices.
- The escape hatch is deliberate for the same reason: `<!-- pr-body-check: skip — <why> -->` in the body, with a **real** stated reason of at least two words, is echoed into the job log. A bare marker with no reason is rejected and the body is checked normally. A gate with no escape hatch gets bypassed with `--admin` instead, and that skips everything.

## Pass/fail summary

The installation passes iff:

- Both scripts exist in the target repo and `python3 -m py_compile` succeeds on each.
- A CI job invokes `pr_body_check.py` on `pull_request` **including the `edited` type**, passes the body through `env:` (never interpolated into `run:`), and feeds the merge-base diff on stdin.
- That job's name appears in the default branch's **required status checks**.
- An incomplete body has been **observed failing** it and a complete body **observed passing** it on the `edited` event — not assumed.
- `[tool.apex]` names the paths whose breakage would be found by an incident, **or** the user has explicitly accepted that the Risk-note rule stays dormant.
- `build_steps()` in `pre_pr_check.py` has been reconciled against the workflow, and the user has been told the ceiling above.

Fail any → the repo has files, not enforcement. The two failure modes that never announce themselves are a **wired job no branch-protection rule requires** and a **`pre_pr_check.py` nobody runs**; both look identical to a working install from the inside, which is why the last three bullets are observed rather than inferred. Hand the finished workflow file to `apex:cicd-review` for the privilege-surface and supply-chain passes before merging it.
