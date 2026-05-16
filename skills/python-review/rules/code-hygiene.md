# Code Hygiene

Imports, layer placement, dead code, documentation, and dependency management.

## Fully-Qualified Absolute Imports — No Relative Imports

**When:** Writing any import in production code or tests.
**Rule:** Always use fully-qualified absolute imports. Relative imports (`.module`, `..module`) are never acceptable.

```python
# ❌ BAD
from .extraction_llm import ExtractionHints

# ✅ GOOD
from myproject.document_intelligence.extraction_llm import ExtractionHints
```

## Imports Inside Methods (Lazy Imports)

**When:** Adding an import that would create a circular import or that is only needed conditionally.
**Rule:** Add the import at the start of the method body (right after the docstring). Use `TYPE_CHECKING` blocks for type-only imports.

## Break Circular Imports With `from __future__ import annotations` + `TYPE_CHECKING`

**When:** Two modules reference each other for type annotations only.
**Rule:** Use `from __future__ import annotations` (makes all annotations strings at runtime) plus a `TYPE_CHECKING` block for the offending imports.
**Why:** Prevents most circular-import bugs without restructuring modules.

## Layer Placement: Domain vs Server

**When:** Deciding where to put a new module.
**Rule:** Pure data models (Pydantic, dataclasses, enums) belong in the domain/core layer. Only put code in the server/web layer if it genuinely requires HTTP, database, or server-side infrastructure.
**How to check:** "Does this module import FastAPI, SQLAlchemy, or an HTTP client? If not, it belongs in the domain layer."

## Use First-Class Internal APIs — Not External Client Transports

**When:** Calling another service from inside the same codebase that owns it.
**Rule:** Use the first-class internal function/client. Never route through the external HTTP client wrapper designed for outside callers.
**Why:** External transports add serialization overhead, wrong error shapes, and create a loopback dependency.
**How to find the pattern:** Search for the internal helper (e.g. `*_internal`, `*_direct`) before writing any new cross-module call.

## Use Canonical Project Utilities — Don't Call Libraries Directly

**When:** About to call a shared infrastructure library (`jsonschema`, `jq`, `structlog`, `httpx`) in a new location.
**Rule:** Check the domain/core layer for an existing project-level wrapper first. Calling the library directly bypasses project-specific extensions (custom keywords, error formats, retry policy).
**Red flag:** A new `import jsonschema` outside the project's own jsonschema module; a new direct `httpx.AsyncClient(...)` outside the shared transport module.

## Don't Import From Legacy / Deprecated Packages

**When:** Tempted to add a new `import` from a package marked deprecated or slated for removal.
**Rule:** Copy the needed function or constant directly into the current codebase. Every new dependency on a deprecated package moves in the wrong direction.
**How to catch in review:** `grep -r "from deprecated_pkg"` — any NEW result (not a legacy pre-existing import) should be rejected.

## New Storage Methods Go in the Base Class — Not Parallel Dialect Mixins

**When:** Adding a new storage capability to a system that supports multiple SQL dialects.
**Rule:** All new storage methods go in the dialect-agnostic base class using SQLAlchemy Core. Use a `_dialect_insert()` factory method for dialect-specific constructs (`ON CONFLICT`). Never create parallel `sqlite/` and `postgres/` mixin files.

## Deferred Platform Implementations: Raise `NotImplementedError`

**When:** A platform-specific backend (e.g., cloud storage) is deferred and the interface has to exist now.
**Rule:** Raise `NotImplementedError("Reason: implementation pending")`. Never leave a stub that silently uses the wrong backend (e.g., local disk in a cloud adapter).

## Keep Documentation in Sync With Code

**When:** Renaming, deleting, or adding a script/function/module.
**Rule:** `grep -r` for references in `*.md`, `*.sh`, and docstrings. Update or delete them in the same commit.

## Update Cross-Module Docstrings When Renaming or Moving

**When:** A refactoring PR moves or renames a module.
**Rule:** Search for the old path in docstrings, `# see also:` comments, and inline comments. Update them all before opening the PR.

## Dead Code Removal Is Not Optional

**Before every PR:**
- Remove any function not called by production code or tests
- Delete superseded scripts (don't comment them out)
- `grep -r "TODO\|FIXME\|HACK\|XXX"` in changed files
- Search for personal UUIDs/emails/paths in shared files

## Don't Commit Unrelated Files

**Rule:** Run `git status` before committing. Never commit planning documents, scratch notes, or files outside the PR scope.

## Docstrings as Contracts

**When:** Writing a public method.
**Rule:** Google-style docstrings for all public methods. If the docstring says "X is treated as Y," code must enforce it. Document destructive side effects (deletion cascades) explicitly — "removes draft schemas" is insufficient if the method also deletes the parent object.

## Don't Pretty-Print JSON Written to Storage

**When:** Serializing JSON for filesystem or object storage writes.
**Rule:** Use `json.dumps(data).encode()` — no `indent=`. Pretty-printing adds whitespace bytes on every read/write for zero runtime benefit.
**Exception:** Debug tooling, local scripts, or config templates meant to be human-edited.

## Flatten Private Helpers With ≤ 2 Callers in the Same File

**When:** A private helper has 1–2 call sites, both in the same file, and the body is ≤ 10 lines.
**Rule:** Inline it. Extraction only justified when the helper adds logic (error handling, logging, transformation) or is called 3+ times.

## Stacked PR Hygiene

**When:** Working on a PR whose dependencies land in earlier PRs.
**Rule:** PR description must state the base branch. Lazy imports of not-yet-existing modules must have a `# Provided by PR #N` comment. Design divergences from established patterns need a docstring explaining why.

## Dependency Management — Pin Exact Versions

**Rule:** Commit lockfiles (`uv.lock`, `poetry.lock`). Run `pip-audit` in CI. Before adding a new dependency, ask:
- Can I implement this in < 50 lines without it?
- Is the package actively maintained (recent commits, open issues addressed)?

## DRY — Rule of Three

**When:** Deciding whether to extract a helper.
**Rule:** Wait until the same knowledge is duplicated three times before abstracting. Two instances is often coincidence; three suggests a real pattern.
**Why:** Premature abstraction produces the wrong abstraction, which is more expensive to fix than the duplication.
