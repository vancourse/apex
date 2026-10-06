# Rulebook: <concept>

<!-- A decision table for one domain concept (design section 8). Every fallback branch
     has a row. The examples table uses PLANTED values only; its hash is the concept
     row's `examples_hash` in concepts.toml, and the operator pins it with
     `rails approve <rulebook> <examples_hash>` before the milestone closes. -->

**Owner:** <semantic entity.column> · <owning function> · <pinning test> · <oracle>

## Rules

| id | rule | measured-on case | refused-by case |
|---|---|---|---|
| r1 | | | |

## Debt

<count of known cases the rules do not yet cover, and where they are tracked>

## Examples (planted values only)

| inputs | expected | rule |
|---|---|---|
| | | r1 |

`examples_hash:` <sha256 of the table above, written by the pinning test>
