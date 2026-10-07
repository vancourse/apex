---
name: fix
description: Fix something broken - a defect, a red check, a wrong behaviour. One issue, one PR that proves it is gone and cannot come back unnoticed.
---

# The fix loop

1. **Reproduce first**, on planted data or the named target, and keep the reproducer: it becomes the test.
   If it cannot be reproduced, say so with what was tried; do not fix a guess.
2. **Find the primary artifact** (the DDL, the function body, the definition site), not a report
   of it. `rails whereis` before concluding anything is missing.
3. **The test fails first**, then the fix. Grep every caller of the function you changed for its own
   workaround of the old behaviour.
4. **Name the gate that should have caught it** in the PR body. If no gate could have, say which rung
   the lesson reaches (gate, hook, prose, dropped) — that is the retro's input.
5. **Ship through the `rails` loop**: intent (tier `fix`), commit, `rails check`, push,
   `rails ship --detected-by <ci|lane|hook|walk|boot|review|audit|operator|agent>` — what found the
   defect FIRST. It lands in the PR body as `Detected-by:`, and `rails metrics` counts it (the
   automation catch rate); a fix shipped without it is invisible to that number.
