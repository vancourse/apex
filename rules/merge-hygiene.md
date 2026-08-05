# Merge Hygiene Rules

Two rules for the moment a branch is synced with its integration branch — the replay, the merge, the conflict resolution — each stated as the rule that would have prevented a measured failure. The failures here are not caught by tests, review, or CI, because in every one of them **the tooling reported success**: the patch applied cleanly, the merge completed, the generator ran. What was wrong was the question asked, not the answer given.

Sibling files: [`landing-a-component.md`](landing-a-component.md) owns getting a component from *sliced* to *merged*; this file owns the mechanics of the sync itself.

## 1. A Clean Apply Is Not Evidence of Correctness

**Rule.** After any patch, rebase, cherry-pick, or merge, **diff the result against the integration branch and confirm the changed-file set is exactly what you intended.** Read the file list, not the exit code.

**Why.** Re-cutting a stacked branch after its parent squash-merged, the replay patch was built from the wrong base. The resulting patch **deleted four files a different PR had just added**. `git apply --3way` applied it cleanly and reported success; nothing conflicted, nothing failed, and the forge would have reported the PR mergeable. The only tell was reading the file list.

Tools report that they succeeded at **what you asked**, not that you asked for the right thing. A three-way apply's job is to reconcile hunks, and it did that job perfectly — against a base that encoded a tree nobody wanted. Exit code 0 is a statement about the patch, not about the repository.

**How to apply.**

- Sync first, then look. Immediately after the merge or replay lands:

  ```bash
  git fetch origin && git diff --name-status origin/main HEAD
  ```

  Because you just synced, every entry in that list should be **yours**. Any `D` you did not author is the alarm — it is a file the integration branch has and your branch does not, which after a sync can only mean your replay removed it.
- Deletions are the entries to read first. An unintended *addition* shows up as review noise and someone catches it; an unintended *deletion* of code that landed while you were working is invisible to everyone downstream, because the diff of what you deleted is not in your commits' story.
- The same read closes rule 2's failure: if a generated artifact appears in the list and you did not regenerate it, you hand-merged it.
- The forge's "mergeable" badge is not this check. It answers "do the hunks reconcile?", which was already true in the failure above.
- **Mechanized:** the `replay` preflight in [`templates/gates/pre_pr_check.py`](../templates/gates/pre_pr_check.py) does this read for you — it reports files the integration branch has that your branch merged in and then lost, and it stays quiet on branches that are merely behind. Its sibling `base` preflight catches the *other* symptom of the same root cause (a branch cut from a base the default branch has since rewritten). Run it, but keep reading the list anyway: the check knows what your branch *lost*, not what you *meant*, and only the second one catches an unintended file you added or changed.

## 2. Generated Artifacts That Are Committed Must Never Be Hand-Merged

**Rule.** A committed file that is a **pure function of the tree** — dependency graph, lockfile, generated client, snapshot, compiled schema — is never merged by hand. Clear the conflict markers by taking **either** side, **regenerate in dependency order**, then verify.

**Why.** Derived files conflict on essentially every merge, and the correct content is **neither side** — it is whatever the generator produces from the merged tree. Resolving one by hand produces a file that is internally plausible, passes review, and does not correspond to any tree that exists.

The failure mode compounds: two generators in one repo **read the file they rewrite**, so a leftover conflict marker kills them with an opaque parse error naming only a line number — a diagnostic that points at the artifact and says nothing about the merge that broke it. Clearing the markers is therefore not cosmetic; it is a precondition for the generator running at all.

A conflict in a pure function of the tree is **never information**. That is the argument for the durable fix rather than the disciplined habit.

**How to apply.**

- Take either side to clear the markers (`git checkout --ours <path>` is fine — the content is about to be overwritten), regenerate, verify the artifact is byte-stable on a second run.
- **Regenerate in dependency order.** If artifact B is generated from a tree that includes artifact A, A regenerates first. Regenerating out of order produces a B that encodes a stale A and is wrong in a way that survives every check.
- **A count that moves after regeneration may not be your change.** Before attributing a delta to your branch, regenerate the artifact on the *integration branch* and compare. A committed artifact that was already stale on the integration branch will shift the moment anyone regenerates it, and the next person to touch it inherits the blame.
- **The durable fix is a merge driver**, not vigilance. Register the generated paths in `.gitattributes` with a driver that resolves by regenerating:

  ```
  # .gitattributes
  path/to/generated.json merge=regenerate
  ```

  ```
  # .git/config (or a repo script that installs it — git does not clone config)
  [merge "regenerate"]
      name = regenerate derived artifact from the merged tree
      driver = <your generator> %A
  ```

  Note the honest limit: merge drivers live in `.git/config`, which is **not cloned**. The driver needs a one-line install step in the repo's setup script, or it protects only the developer who configured it. Lacking that, `merge=binary` at least converts a silent bad hand-merge into a loud conflict.
- Never let a generated artifact be the reason a merge is "hard." If resolving one is taking thought, that is the signal you are doing the wrong operation, not that you need to concentrate.

## Where these rules are applied

| Rule | Applied in |
|---|---|
| 1. A clean apply is not evidence | `apex:pr-discipline` §3 (re-cutting a stack) + §5 (self-review checklist), `apex:ai-pre-review-checklist` (Definition of Ready), `apex:verification-before-completion` (the merge/replay row), `templates/gates/pre_pr_check.py` `preflight` (the `replay` check — this rule, mechanized; plus `base`, the sibling symptom) |
| 2. Generated artifacts are regenerated, never hand-merged | `apex:pr-discipline` §3 (generated code doesn't count toward the LOC cap — and doesn't get hand-resolved either), `apex:cicd-review` Pass 5 (determinism — a pipeline that can't reproduce the artifact can't verify it), `rules/review-risk.md` (lockfile/generated-type touch points) |

Skills should reference this file by section rather than restating the rule. Apply it in the skill's own context; let the canonical statement live here.
