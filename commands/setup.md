---
description: "[USER] Install apex's recommended companions — superpowers / pr-review-toolkit (skills apex chains) and an optional large-codebase context tool (Graphify / Serena / Claude Context). Runs what it can, prints exact commands for the rest."
---

Guided installer for apex's recommended companion plugins and large-codebase
context tooling. **You are an assistant following these steps**, not a shell
script — run what you safely can via Bash, and for anything that needs
`/plugin` (a Claude Code built-in you cannot invoke from here) or a host
package manager, print the **exact** command for the user to run and tell them
to restart Claude Code afterward.

## Step 0 — Detect what's already present

- Check installed plugins / skills: look for `superpowers`, `pr-review-toolkit`,
  `frontend-design` (e.g. inspect `~/.claude/plugins/`), and report which are
  already present so you don't re-install.
- Check host tooling for the codebase-graph option: `command -v uv pipx graphify serena` — record what exists.
- Ask the user which groups they want (default: the SDLC companions; the
  codebase-graph tool is opt-in). Don't install anything not chosen.

## Step 1 — SDLC companions (skills apex chains)

These back apex commands directly — **without them, the chaining commands degrade
or print a missing-dep message** (see README → *Recommended companions* and
*Companion plugins* in HOWTO):

| Plugin | apex uses it for |
|---|---|
| `superpowers` (`obra/superpowers`) | `/apex:prd` (brainstorming → writing-plans), `/apex:impl-plan` (writing-plans), the 2-agent adversarial pair (dispatching-parallel-agents), the TDD red-green loop `test-strategy` assumes, and `systematic-debugging` |
| `pr-review-toolkit` | `/apex:review-pr`'s 6 cooperating specialist agents |
| `frontend-design` (`anthropics/claude-plugins-official`) | polished UI work (optional) |

Print these for the user to run (they require the `/plugin` built-in), then
**restart Claude Code**:

```text
/plugin marketplace add obra/superpowers
/plugin install superpowers@superpowers-dev

/plugin marketplace add pr-review-toolkit      # or its official marketplace entry
/plugin install pr-review-toolkit

/plugin marketplace add anthropics/claude-plugins-official
/plugin install frontend-design@claude-plugins-official   # optional
```

## Step 2 — Large-codebase context tool (optional, pick ONE)

For big repos, a structural index lets apex's `recon` (Step 1) and everyday
navigation skip blind grepping. Pick the one that matches how you work — see
README → *Large-codebase context tools* for the trade-offs:

**A) Graphify** — committed knowledge graph + a PreToolUse hook (closest to
"map it once, reuse every session"). Local AST extraction, 33 languages. You
*can* run the install via Bash:

```bash
uv tool install graphifyy      # or: pipx install graphifyy
graphify install               # registers the /graphify skill + CLAUDE.md directive + hook
```

Then have the user run `/graphify .` in the repo, add the auto-rebuild hook, and
commit the output:

```bash
graphify hook install
git add graphify-out/ && git commit -m "chore: add codebase knowledge graph"
```

> Note the **ephemeral** rule (recon Step 1): the committed graph is a fast
> navigation aid, not ground truth — the post-commit hook keeps it fresh, and
> you still read the actual functions for their contracts.

**B) Serena** (`oraios/serena`) — live LSP symbol navigation + safe edits, no
index to maintain (never stale). Install as an MCP server per its README.

**C) Claude Context** (`zilliztech/claude-context`) — semantic vector search
over millions of LOC; requires a Milvus/Zilliz vector DB. Install as an MCP
server per its README.

## Step 3 — Verify + report

- Re-check `command -v` for any host tools you installed.
- Remind the user that **plugins only register after a Claude Code restart**.
- Print a short checklist of what's installed vs. what's left for the user to
  run manually, with the exact remaining commands.

## Notes

- This command **never** declares these as `plugin.json` dependencies — apex's
  manifest stays dependency-free on purpose (a single unresolved name silently
  fails the whole install; see README). This is a guided installer, not a
  dependency manifest.
- Everything here is optional. apex works without any of it; the companions just
  make the chaining commands and large-repo navigation better.
