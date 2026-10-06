# rails

A Claude Code plugin that keeps application building on the rails. It was apex; it is now the
harness the [rails design](docs/design/rails/rails-design-v1.2.md) specifies, built from 1,007
escaped defects across two codebases and 4,253 operator messages.

Its premise: in this toolchain only four things can refuse — a `PreToolUse` deny, a `Stop` block,
a required GitHub check, and a git hook. Every rule here lives in one of them, or is labelled
judgment. Prose that a gate can carry is deleted.

## What it does

| Piece | What it refuses or records |
|---|---|
| **One dispatcher** (`hooks/rails_hook.py`) | Every hook event goes through one process that routes to the gates in `hooks/gates.toml`, on `Bash` *and* `PowerShell`, with backslash paths normalised. A missing gate module says `RAILS: gate X missing; unguarded` instead of failing silently. |
| **Deny family** | `git stash` (a stack every worktree shares), pipes that mask an exit code, `.env` and secret reads, here-docs writing files, servers launched where the harness reaps them, pushing a merged PR's branch, destructive commands; in shadow: merging any way but auto-squash, agent-posted commit statuses, a second PR per worktree. |
| **Local-first CI** | `rails check` runs every lane the diff selects (`rails/lanes.toml`) on the laptop and seals a marker per commit; `rails post` sets one `rails/<lane>` status per lane; the PR's required `gate` (the `verify-lanes` action) only reads them. A PR costs about one billed CI minute. |
| **Git hooks** | `rails adopt` points `core.hooksPath` here and chains the repo's own hooks. pre-push refuses without a check marker, under the operator's `hold`, or when the leak check finds a household value (or has no fresh snapshot to compare with). |
| **Leak check** | Compares text against a salted-hash snapshot of the household's real values — amounts, booking ids, descriptors — on pushed lines, commit messages, `gh` bodies and titles, and subagent prompts. Never prints a value. |
| **Session loop** | Claim before the first edit; show the intent and let the operator's next message ack or correct it; one PR per worktree with auto-squash armed; the turn cannot end on an armed PR whose closing step has no passing walk receipt. |
| **Receipts** | Every lane, walk and ship writes a sealed receipt. Tamper-evident, not tamper-proof: a receipt no command was seen writing is reported `forged`. |
| **Starter kit** | `rails new <app>`: a walking skeleton where contracts, settings, roots, the clock, limits, concepts, RLS and the auth matrix are already tests that fail on a planted defect. |

New refusals ship in **shadow mode** for 7 days (`would-deny` in the firing log) before they refuse
anyone. `rails metrics` reports what fired, what it cost, and CI minutes against the budget.

## Install (the operator, once per machine)

```bash
git clone https://github.com/vancourse/apex ~/devenv/repos/apex
python3 ~/devenv/repos/apex/bin/rails enable
```

`rails enable` registers this checkout as a directory marketplace (so every worktree loads the same
copy, in place), enables `rails@rails`, disables the old `apex@apex`, installs `rails` / `rails.cmd`
shims in `~/.local/bin`, and adopts the current repo's git hooks. It backs up
`~/.claude/settings.json` first and refuses to run inside an agent's tool call.

Then, in each repo: `rails adopt`, a `rails/lanes.toml`, and a PR workflow whose `gate` job is
`uses: vancourse/apex/actions/verify-lanes@<sha>`.

## The loop

```text
rails claim "#123"          # before the first source edit
.rails/intent.md            # shown at turn end; the operator's next message acks or corrects it
git commit ...              # never blocked
rails check                 # lanes the diff needs; seals a marker for HEAD
git push                    # pre-push: marker, hold, leak check
rails ship                  # one Ready PR, auto-squash armed, statuses posted
rails walk                  # step ids pass on the named target
used #<milestone> <task>    # the operator, after using it
```

The operator's words are `hold`, `release`, `used` and `approve`. Everything else is evidence.

## Layout

```text
.claude-plugin/        plugin + marketplace manifests (name: rails)
hooks/                 hooks.json (one dispatcher), rails_hook.py, gates.toml (the registry)
rails/                 the package: dispatch, gates/, shell/, check, verify, githooks, leak, claims, ...
git-hooks/             wrappers for every git hook -> bin/rails-githook
actions/verify-lanes/  the composite action a repo's PR gate uses
bin/                   rails, rails.cmd, rails-githook
kit/                   the starter kit template behind `rails new`
skills/                rails, release, fix, retro, and six review skills
agents/                recon, reviewer-coop, reviewer-adversary (read-only tools)
templates/             intent, spec, adr, milestone, rulebook, PR template, session contract
docs/design/rails/     the design, its evidence, drafts and research
tests/                 the suite (runs on ubuntu-latest and windows-latest)
```

Everything under `rails/` is standard library only: hooks start a fresh interpreter on every tool call.

## Governance

A gate earns its row in `hooks/gates.toml` (plugin) or `rails/gates.toml` (repo) with the defects it
cites, a planted defect it must refuse, its false-positive count and where that was measured, and its
class: `lockout` rows (data leaving, shared refs) never expire on silence; `friction` rows silent for
60 days are deleted or re-justified. `tests/test_gates_registry.py` fails an unregistered gate, a
missing field, or a planted defect that no longer trips its gate.
