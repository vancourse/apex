# Maintaining apex

Discipline for anyone modifying **apex itself** — the plugin's own skills, commands, hooks, and docs — as distinct from *using* apex on other projects. These notes capture failure modes the Copilot bot reviewer reliably catches on apex PRs, surfaced here so contributors can avoid the cost up front.

If you're new to apex, this is *not* the right entry point — read [README.md](README.md) and [HOWTO.md](HOWTO.md) first.

## When this fires

Apex's [`hooks/suggest-skill-on-edit.sh`](hooks/suggest-skill-on-edit.sh) reminds you to read this file when you edit anything under `skills/`, `commands/`, `hooks/`, or `rules/` *inside the apex plugin repo itself* (detected via `.claude-plugin/plugin.json`). The reminder doesn't fire in projects that merely use apex — only when contributing to apex.

## 1. Pair patterns are NOT all the same — verify each callsite before consolidating

When introducing a "canonical dispatch mechanism" referenced by multiple skills (e.g., [`apex:adversarial-pair`](skills/adversarial-pair/SKILL.md)), **do NOT** grep-and-replace `via superpowers:dispatching-parallel-agents` → `via apex:adversarial-pair` blindly across all review skills.

Some apex review skills describe a **two-attacker** pair (different inputs, both adversarial) — NOT a **cooperative+adversarial** pair (same input, opposite framings). The two patterns are not interchangeable; mistaking one for the other puts the wrong framing prompt in front of the dispatched agent.

### Known two-attacker pairs (NOT `apex:adversarial-pair`)

| Skill | Pair shape |
|---|---|
| [`skills/design-review/SKILL.md`](skills/design-review/SKILL.md) §"Adversarial pair pattern" | Agent A walks the 6 passes in attack mode against the design doc; Agent B runs `apex:threat-model` heavyweight against the attack surface. Both adversarial, different inputs. |

Why this exists: `design-review` is itself already the *adversarial half* of `design-feature`'s cooperative authoring voice. A "pair" inside design-review can't add another cooperative agent — the cooperative voice is upstream. So design-review's pair multiplies the attack lens instead.

### Known cooperative+adversarial pairs (`apex:adversarial-pair` applies)

The apex review skills that explicitly reference `apex:adversarial-pair` as their canonical pair-dispatch mechanism (per the PR #22 consolidation):

`prd-review`, `design-feature`, `impl-plan-review`, `threat-model`, `adr-review`, `architecture-design`, `observability-review`, `data-migration-review`, `security-review`.

Other review-oriented skills in the repo (e.g. `postgres-review`, `test-coverage-audit`, `python-review`, `typescript-review`) do **not** currently use the pair pattern at all — they run as a single agent. When promoting one of those to a pair pattern, decide consciously whether it's cooperative+adversarial (use `apex:adversarial-pair`) or some other shape (document the divergence inline).

### Discipline

Before mechanically replacing the dispatch reference in any review skill, **read the pair-pattern section** and verify the dispatched agents' framings match `apex:adversarial-pair`'s cooperative+adversarial split. If the section describes a different shape (two attackers on different inputs; cooperative-only sanity check; etc.), do not collapse it into `apex:adversarial-pair` — document the divergence inline instead.

PR #22 spent 3 of its 5 Copilot review rounds unwinding one bad blanket substitution. Don't repeat the mistake.

## 2. Slash-menu count drifts — grep the docs tree before adding `/apex:<name>`

The "N entry-point commands" count is hardcoded as prose in **at least 6 doc sites**. Adding (or removing) any `/apex:<name>` command without updating every site leaves the docs internally inconsistent.

### Known sites holding the count

| File | Location | Form |
|---|---|---|
| [`README.md`](README.md) | "small slash menu" paragraph (~line 56) | `the ~N things you drive by hand` |
| [`README.md`](README.md) | Note in the CLAUDE.md section (~line 229) | `Only the N **entry-point** commands` |
| [`README.md`](README.md) | Install/paste block in the setup walkthrough (~line 218) | `the N-command cheat sheet` |
| [`commands/help.md`](commands/help.md) | Header of the cheat sheet (~line 10) | `the entire /apex: slash menu (N entry-point commands)` |
| [`commands/help.md`](commands/help.md) | "THE SLASH MENU IS INTENTIONALLY SMALL" footer (~line 57) | `Only the N entry-point commands above` |
| [`WALKTHROUGH.md`](WALKTHROUGH.md) | Auto-fire skills paragraph (~line 100) | `limited to the N entry-point commands` |

### Grep command

Run this from the apex repo root before opening a PR that adds or removes a slash command:

```bash
grep -rEn '[0-9]+[* ]+entry-point|[0-9]+-command cheat sheet|~?[0-9]+ things you drive' \
  --include='*.md' --exclude-dir=node_modules .
```

Notes on the pattern:
- `-E` (ERE) for portable `+` / `|` (works under BSD grep on macOS as well as GNU).
- `--exclude-dir=node_modules` excludes the directory, not the substring (cleaner than `| grep -v node_modules`).
- `[* ]+` between the digit and `entry-point` swallows markdown bold (`14 **entry-point**`) and plain space alike — without this the `entry-point` form in `README.md:232` would slip through.
- Three alternations cover the three phrasings used across the 6 sites in the table above.

Update every hit to the new count in the same commit. Also add a row to `commands/help.md`'s actual command list.

### Why this exists

PR #22 added `/apex:adversarial-pair`. Copilot caught the count drift in rounds 3, 4, AND 5 — one site per round — because each missed site only surfaced once Copilot re-read the diff against the updated neighbors. Four review cycles burned on a class of issue that one pre-PR grep catches in 5 seconds.

## Why these aren't skills

These are *maintainer* discipline, not *user-facing* methodology. They fire only when contributing to apex itself, which is a narrow audience. Wrapping them as skills would add noise for every apex user not maintaining the plugin. The PreToolUse hook surfaces this doc only when the edited path is inside the apex plugin repo, which is the right scoping.

## Adding a new lesson here

When a class of issue burns ≥2 Copilot rounds across an apex PR, capture it here. The schema is informal — title + "why this exists" + actionable discipline + (optional) grep command or other detection mechanism. Keep the tone direct: tell the next maintainer what to *do*, not what to *think*.
