---
description: "[USER] Cut a release of THIS project — semver decision audited against the diff, user-facing changelog, readiness gate (tests at the SHA, migration notes, rollback path), tag → build-from-tag → publish, post-release bake watch"
---

Invoke the `release-readiness` skill from the apex plugin for this task. Read its SKILL.md and follow it.

Run the five passes in order and do not tag until Pass 3 (the readiness gate) is clean. If the project has a release script, prefer it for Pass 4's mechanics; if it doesn't and this is the second manual release, offer to write one (apex's own `scripts/release.sh` is the reference shape).
