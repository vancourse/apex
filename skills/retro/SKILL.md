---
name: retro
description: Close a session by routing ONE finding to the strongest rung it reaches - a gate or test, else a hook, else prose, else dropped.
---

# The retro loop

1. **One finding, with a number.** What went wrong this session that a mechanism could have
   caught? Use your own turn history, never a parse of transcript files.
2. **Route it to the strongest rung:**
   - a **gate or test** (`rails/gates.toml` row with cites, a planted defect, an FP count measured on
     the real tree, and `required_by`);
   - else a **hook** (plugin `hooks/gates.toml` row; 7 days in shadow before it refuses);
   - else **prose**, only under `## Judgment` or with `-> enforced by: <path>`;
   - else **drop it**. Dropping is the common case and not a failure.
3. **Write it where it lives** before the session ends: the PR body, an issue (one per session), or
   the registry. A lesson only in chat is gone next session.
4. **Delete one thing** if the metrics say a mechanism earned nothing (`rails metrics`).
