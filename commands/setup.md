---
description: "[USER] Install apex's companions — superpowers / pr-review-toolkit / frontend-design (via the claude CLI), an optional large-codebase context tool (Graphify / Serena / Claude Context), and optional gastown-ecosystem tooling (beads issue tracking, gastown orchestrator). Installs for real when the claude CLI is available; falls back to printing exact commands."
---

Guided installer for apex's companion plugins and optional tooling. **You are an
assistant following these steps**, not a shell script. Prefer to *actually
install* via the `claude` CLI and host package managers; only fall back to
printing commands when a tool genuinely cannot be driven from here. Always
remind the user to **restart Claude Code** at the end — plugins register at
session start.

## Step 0 — Detect the environment

Run these and record the results; they decide *how* you install, not just *what*:

```bash
command -v claude && claude --version        # can we install plugins headlessly?
command -v brew uv pipx                       # host package managers available?
command -v graphify serena bd                 # context tool / beads already present?
claude plugin list 2>/dev/null                # which plugins are already installed (CLI view)
```

- **If `claude` is on PATH** (true in the CLI/terminal, and in desktop when the
  binary is installed): you can install plugins **directly** with
  `claude plugin …` — this is the happy path.
- **If `claude` is NOT on PATH**: fall back to printing the `/plugin …` commands
  for the user to run in-app.

Then **ask the user which groups they want** with a choices prompt
(AskUserQuestion) — don't install anything not chosen:
1. SDLC companions: superpowers + pr-review-toolkit (recommended), frontend-design (optional, UI work).
2. Large-codebase context tool: Graphify / Serena / Claude Context / skip (pick one).
3. Gastown-ecosystem tooling (optional, orthogonal to apex's gates): beads (`bd`, issue tracker) and/or gastown (`gt`, multi-agent orchestrator — advanced; installing it pulls beads in).

## Step 1 — SDLC companion plugins

These back apex commands directly — **without them the chaining commands degrade**
(superpowers powers `/apex:prd`, `/apex:impl-plan`, the TDD loop, and
`systematic-debugging`; pr-review-toolkit powers `/apex:review-pr`'s 6 specialist
agents; frontend-design is optional polish). The 2-agent adversarial pair is owned
by apex via `apex:adversarial-pair` — no superpowers dependency.

**If the `claude` CLI is present**, install for real (use `--scope user` so they
are available everywhere and never write a project-local `.claude/settings.json`):

```bash
claude plugin marketplace add obra/superpowers
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install superpowers@superpowers-dev      --scope user
claude plugin install pr-review-toolkit@claude-plugins-official --scope user
claude plugin install frontend-design@claude-plugins-official   --scope user   # only if chosen
```

Run only the lines for groups the user chose. `claude plugin install` is
non-interactive (no confirmation flag needed). Skip any plugin already shown by
`claude plugin list`.

**If the `claude` CLI is absent**, print the in-app equivalents instead and tell
the user to run them, then restart:

```text
/plugin marketplace add obra/superpowers
/plugin install superpowers@superpowers-dev
/plugin marketplace add anthropics/claude-plugins-official
/plugin install pr-review-toolkit@claude-plugins-official
/plugin install frontend-design@claude-plugins-official   # optional
```

## Step 2 — Large-codebase context tool (optional, pick ONE)

A structural index lets `apex:recon` (Step 1) and everyday navigation skip blind
grepping. apex only **installs** the tool here; the tool then **maintains its own
freshness** (recon queries it, the tool keeps it current). See README →
*Large-codebase context tools* for trade-offs.

**A) Graphify** — committed knowledge graph + auto-rebuild hook ("map once, reuse
every session"). Installable via Bash:

```bash
uv tool install graphifyy      # or: pipx install graphifyy
graphify install               # registers the /graphify skill + CLAUDE.md directive
```

Then, in the target repo: `/graphify .` to build the graph, and
`graphify hook install` so each commit refreshes it (code-only, no API key).
**Gitignore the output** — `graph.json` is large and per-machine:
`echo '/graphify-out/' >> .gitignore`.

> **Ephemeral rule** (matches recon): the graph is a navigation aid, *not the
> source of truth* — the hook keeps it fresh; you still read the actual functions
> for their contracts. Presence is not freshness.

**B) Serena** (`oraios/serena`) — live LSP symbol navigation, never stale. Install
as an MCP server per its README.

**C) Claude Context** (`zilliztech/claude-context`) — semantic vector search;
needs a Milvus/Zilliz vector DB. Install as an MCP server per its README.

## Step 3 — Gastown-ecosystem tooling (optional)

Only the pieces the user chose. Both are **orthogonal to apex's gates** —
work-tracking / orchestration, not part of the SDLC methodology.

**Beads (`bd`)** — issue tracker (local Dolt DB, hash-based IDs that survive
parallel-agent merges). Install globally:

```bash
brew install beads                                                        # macOS (pulls dolt)
# or, cross-platform:
curl -fsSL https://raw.githubusercontent.com/gastownhall/beads/main/scripts/install.sh | bash
```

Then tell the user it is **per-repo**: in each project, run `bd init --stealth`
(keeps `.beads/` local) and optionally `bd setup claude` to wire SessionStart
context. Do not run `bd init` for them without knowing the target repo.

**Gastown (`gt`)** — multi-agent workspace orchestrator (polecats / refinery /
merge-queue). **Heavier and advanced** — worth it for broad parallel work across
many work-items, overkill for a single focused change. Installing it **pulls
beads + dolt as dependencies**, so choosing Gastown gives you Beads too:

```bash
brew install gastown      # macOS; pulls beads + dolt
```

Then `gt install ~/gastown` once (creates the HQ workspace), and `gt init` inside
each git repo you want it to manage. See the gastown README for non-macOS install.
Don't run `gt install` / `gt init` for the user without confirming the location/repo.

## Step 4 — Verify + report

- Re-run `claude plugin list` and `command -v graphify bd` for what you installed.
- Print a checklist: ✅ installed vs 🔲 left for the user, with exact remaining commands.
- **Remind the user to restart Claude Code** — newly installed plugins/skills
  only register at session start.

## Notes

- apex's `plugin.json` **never** declares these as dependencies — the manifest
  stays dependency-free on purpose (one unresolved name fails the whole install).
  This is a guided installer, not a dependency manifest.
- Everything here is optional. apex works without any of it; the companions just
  make the chaining commands, large-repo navigation, and work-tracking better.
- Prefer `--scope user` for plugins. Project scope writes a tracked
  `.claude/settings.json`, which is rarely what you want for global tooling.
