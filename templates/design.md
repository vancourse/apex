# <Feature> — Design

**Status:** Draft | **Frozen <date>**
**Upstream:** `prd.md` (frozen <date>) · `recon.md`

## Reuse verdict

The design must either **use** the primitives recon named or **justify** why each cannot
be extended. This is the same table the PR template asks for, decided here first, where
changing your mind is still cheap.

| Capability needed | Existing primitive (`file:line`) | Verdict |
| --- | --- | --- |
|  |  | USE / EXTEND / JUSTIFIED-NEW |

A design with no USE or EXTEND rows is claiming the platform had nothing to offer.
That is occasionally true and usually a sign recon was skipped.

## The shape

What gets built, in the smallest form that serves the PRD's scenarios. Prefer the
subtractive version: the design that queries an existing primitive beats the one that
stores and reconstructs what the system already hands you.

## Alternatives rejected

At least one, with the reason. "No alternative was considered" is a finding.

## Integration

What this talks to, and across which boundary. If it cannot be served by the frozen
architecture, stop and write an amendment ADR before continuing — see `docs/adr/`.

## Failure modes

| What fails | Detected how | Behaviour |
| --- | --- | --- |

## Attack surface

Inputs that cross a trust boundary, data classifications touched, and any privilege
transition. If any row is non-empty, run apex:threat-model against the architecture's
auth and data-classification ADRs.

## Deferred

What is deliberately not in the first cut, and what would trigger building it.

## Open questions discharged

| PRD question | Answer |
| --- | --- |

## Freeze record

| Date | Change | Why |
| --- | --- | --- |
