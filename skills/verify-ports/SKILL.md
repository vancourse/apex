---
name: verify-ports
description: Verify code ported from another repository — the source repo's assumptions about destination schema, product state, UX conventions, and external formats are stale by default. Fires when copying / porting / adapting code from another repo, sister project, or prior implementation. Keywords: port, port from, copy from, adapt from, paste from, sister repo, source repo, reference implementation, prior implementation, lift from.
---

# Verify Ports — Don't Trust Them

When porting code from another repository, **the source repo's assumptions about the destination's schema, UX, and product state are stale by default.** Treat the port as a starting sketch, not as authoritative.

## The Five-Point Verification

Before designing changes from a port, write down every assumption it carries and verify each against the destination's current code:

### 1. Schema

Read the OpenAPI types / Zod schemas / Pydantic models in the destination. Field names lie (`private_key_path` ≠ "file path"). Type unions evolve. Optional vs required changes between versions.

**How to verify:** grep for the type the ported code consumes. Read the actual field definitions. Note any divergence from what the ported code expected.

### 2. Product state

Search recent commits in the target area. Features get added, deprecated, or moved between layers. Don't model what existed in the source repo six months ago.

**How to verify:** `git log -p` on the destination's relevant directory. Check for recent feature additions, deprecations, or migrations that the ported code wouldn't know about.

### 3. UX conventions

Check the destination's existing forms, banners, and error messages. The source repo's UX choices may not match.

**How to verify:** find a similar feature in the destination. Compare the form fields, button placement, error display, banner copy. Adopt the destination's conventions, not the source's.

### 4. External format reality

Read the upstream service's docs (cloud account URL formats, DSN strings, OAuth callback URLs, webhook signature schemes). Users paste what cloud UIs emit today, not what old client libraries documented.

**How to verify:** open the actual third-party service docs. Compare against the regex / parser / validator in the ported code. The source repo's regex may have been correct in 2022 and stale in 2025.

### 5. Defensive code

The source repo's defensive checks (regexes, runtime guards, prototype-pollution tests, exception classes) may have solved problems specific to that repo. In the destination, they may be redundant or actively conflict with intended use cases.

**How to verify:** for each defensive block in the ported code, ask: what attack / failure mode is this guarding against? Does that mode apply here? If the destination already validates at a different layer, the duplicate guard is noise (or worse, blocks valid input).

## Why this matters

A single ported PR commonly carries 4–5 stale assumptions:

- Dead credential type that the destination removed
- Missing newer auth mode the source didn't support
- File-path vs string credential model mismatch
- Missing recent external URL format
- Defensive proto-pollution test that prevents legitimate flows

Each becomes a separate review comment. Verifying upfront catches all of them in one pass — and avoids the painful "fix one, find another" cycle of round-tripping with reviewers.

## When to invoke this skill

- About to copy code from another repo
- Looking at a "reference implementation" in a sister project
- Adapting a pattern that worked in a previous repo
- The user says "do it like our other service did" / "lift from project X" / "port from the old service"

## Reporting findings

Before writing destination code, surface the assumptions table:

```
Assumption                          Source                       Destination reality
==================================  ===========================  ============================
Credential type is `KeyFile`        old client lib v1.2          deprecated in v2; use `Token`
URL format is `https://...`         AWS account ID format        Snowflake account locator
Field `private_key_path` is a path  source repo                  destination expects PEM string
Defensive __proto__ guard           source repo's history        destination validates at layer N
```

Then propose the design accounting for the destination's reality, not the source's.

## Relationship to other skills

- **`api-surface-review`** — port the wire format AND check it against the producer's actual current shape. The port is a hypothesis; the surface review tests it.
- **`sdlc-methodology` §1a (reconnaissance)** — codebase reconnaissance applies here too: grep for sibling implementations before adopting the port.
