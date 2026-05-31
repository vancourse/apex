# apex — HOWTO

A quickstart for installing, using, updating, and uninstalling the **apex** Claude Code plugin.

For the full methodology, see [WALKTHROUGH.md](WALKTHROUGH.md) (narrative idea→feature path) and [FLOW.md](FLOW.md) (phase × skill matrix). For the reference table of every skill and command, see [README.md](README.md).

---

## 1. Install + first run

apex ships as a single-plugin Claude Code marketplace at `vancourse/apex`. Install it from inside Claude Code:

```text
/plugin marketplace add vancourse/apex
/plugin install apex@apex
```

Verify the install in a **new** Claude Code session (the slash-command list is loaded at session start):

```text
/apex:help
```

You should see the apex cheat sheet — `[USER]` commands you type at phase boundaries, `[AUTO]` skills the model fires automatically, and the SDLC workflow at a glance. If the command is missing, the plugin didn't activate — see *Updating* below.

---

## 2. The 6-command workflow

apex is designed so you type ~6 commands across an entire feature; everything else fires automatically based on phase + file paths. The full narrative is in **[WALKTHROUGH.md](WALKTHROUGH.md)**. Quickstart:

| Phase | You type | What fires automatically after |
|---|---|---|
| **Spec** — author + freeze a PRD | `/apex:prd` | `prd-review` skill (audit + freeze) |
| **Architecture** — one-time at project start | `/apex:arch` | `adr-review` skill per ADR |
| **Design** — design a feature against the frozen PRD | `/apex:design` | `design-review` skill (adversarial re-pass + freeze) |
| **Plan** — implementation plan against the frozen design | `/apex:impl-plan` | `impl-plan-review` skill (layered stack + sequencing + tests + rollout + reversibility) |
| **Build** — just describe the task | *(no explicit command)* | Language reviews, threat-model triggers, test-strategy, verification-before-completion |
| **PR** — open + review | `/apex:copilot-review` | `pr-discipline`, `pr-review-primer`, `summarize-changes`, `responding-to-review` |

**Optional but useful:**

- `/apex:review-pr` — heavy multi-agent pre-PR review, dispatches 6 cooperating specialists in parallel (needs the `pr-review-toolkit` companion plugin — see §3).
- `/apex:spec-view` — renders a PRD / ADR set / design doc as a disposable offline rich-HTML view for a non-engineer reviewer.
- `/apex:test [layer]` — focuses test-strategy on one of the 8 test layers; advisory, does not run your suite.
- `/apex:flow` — catch-all router if you're unsure which gate to enter.

**Skip rule for small work:** a one-file fix or a typo doesn't need the gate chain. Use `/apex:flow` for the reconnaissance + adversarial pass and proceed.

---

## 3. Companion plugins (soft dependencies — install separately)

apex deliberately defers a few capabilities to other plugins rather than re-implement them. Install whichever you need:

```text
# superpowers — brainstorming, writing-plans, TDD red-green loop, parallel agents
/plugin marketplace add obra/superpowers
/plugin install superpowers@superpowers-dev

# pr-review-toolkit — backs /apex:review-pr's 6 cooperating specialist agents
/plugin marketplace add pr-review-toolkit  # use the official marketplace entry, or its git source
/plugin install pr-review-toolkit
```

What apex defers to each:

| Companion | apex uses it for | Without it… |
|---|---|---|
| `superpowers:brainstorming` | `/apex:prd` step 1 — explore intent before drafting | `/apex:prd` will say it's missing |
| `superpowers:writing-plans` | `/apex:prd` step 2 + `/apex:impl-plan` | Same |
| `superpowers:test-driven-development` | The red-green loop that `test-strategy` assumes | apex still tells you *what* to test + *where* + *what to mock*; you'll write the loop manually |
| `superpowers:dispatching-parallel-agents` | The 2-agent cooperative+adversarial pair (default for non-trivial designs/plans) | You can still run the single-agent inline adversarial pass |
| `superpowers:systematic-debugging` | Debug discipline (apex doesn't own debugging) | Use your own approach |
| `pr-review-toolkit` | `/apex:review-pr` 6-specialist multi-agent review | `/apex:review-pr` won't dispatch its agents |

apex remains usable without any of these — the affected commands will degrade gracefully or print a missing-dep message.

---

## 4. Updating + uninstalling

### Update to a new version

```text
/plugin update apex@apex
```

This pulls the latest tagged release from `vancourse/apex` into a versioned cache under `~/.claude/plugins/cache/apex/apex/<version>/`. Restart your Claude Code session for the new commands and skills to register.

### Uninstall

```text
/plugin uninstall apex@apex
```

Optionally also remove the marketplace entry if you don't plan to reinstall:

```text
/plugin marketplace remove apex
```

Uninstall removes the cached plugin directory and the entry from `~/.claude/plugins/installed_plugins.json`. Nothing in your project repos is touched.

### Troubleshooting

- **Slash commands don't show up after install.** Start a new Claude Code session — the command list is snapshotted at startup.
- **`/apex:help` shows stale paths after an update.** The cheat sheet refers to `<version>` placeholder; check `~/.claude/plugins/installed_plugins.json` for the actual version installed.
- **Want to test local changes before publishing?** Point `/plugin install` at a local path: `/plugin install /absolute/path/to/apex-checkout`. This installs from the working tree instead of the git marketplace.

---

## Where to go next

- **[WALKTHROUGH.md](WALKTHROUGH.md)** — full idea → shipped feature narrative, in order.
- **[FLOW.md](FLOW.md)** — phase-by-phase routing reference.
- **[README.md](README.md)** — every skill and command, with descriptions.
- **[CHANGELOG.md](CHANGELOG.md)** — what changed in each release.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — how to propose changes (apex follows its own `pr-discipline`).
