# Logging & Observability

Standards for structured logging, log levels, error IDs, and metrics.

## Use `structlog` — Never `logging.getLogger`

**When:** Adding any log statement in a project that has standardized on `structlog`.
**Rule:** `logger = structlog.get_logger(__name__)`. Never `logging.getLogger(__name__)`. Consider enforcing with ruff `TID253`.
**Exception:** The single module that configures the stdlib logging system structlog wraps.

## Structured Logging — Context Arguments, Not F-Strings

**When:** Logging any event.
**Rule:** Pass context as keyword arguments. Never format strings for structured data.

```python
# ✅ GOOD
logger.info("Processing work item", user_id=user_id, work_item_id=work_item_id, status="started")

# ❌ BAD
logger.info(f"User {user_id} processing work item {work_item_id} - started")
```

**Why:** Structured logs are queryable and parseable; formatted strings are not.

## Log Levels — INFO for State Changes, DEBUG for Per-Request Noise

**When:** Choosing a log level.

| Level | Use for |
|---|---|
| `DEBUG` | Events that fire on every request: cache hits, race-condition resolutions, per-item iterations |
| `INFO` | Meaningful state changes visible at a glance in production ops: creations, completions, config updates |
| `WARNING` | Unexpected but recoverable conditions |
| `ERROR` | Errors that need attention (include `exc_info=True` or structured fields) |
| `CRITICAL` | System-level failures |

**Rule:** If a log line fires on every file upload or API call, use `DEBUG`. `INFO` is for events worth noticing in a production ops view.

```python
# ❌ BAD: INFO floods production logs
logger.info("Artifact found by hash", artifact_id=artifact.id, cache_hit=True)

# ✅ GOOD
logger.debug("Artifact found by hash", artifact_id=artifact.id, cache_hit=True)
logger.info("Artifact created", artifact_id=artifact.id, path=artifact_path)
```

## Error IDs — Every Error Gets a Unique ID for Tracing

**When:** Returning an error response.
**Rule:** Include a `Field(default_factory=lambda: str(uuid4()))` `error_id` on error response models. Log the same `error_id` for correlation.

## Metrics & Telemetry — Track Key Performance Indicators

**When:** Building any endpoint or background worker.
**Rule:** Track request latency, error rates, resource usage, and key business metrics (queries processed, files uploaded). Without metrics, production incidents are blind.

## Redact PII Before Logging

**When:** Logging data that may contain sensitive fields.
**Rule:** Sanitize before logging. Never log `password`, `token`, `api_key`, or `email` in plaintext. See `rules/security.md`.

## Docstring Accuracy — Treat Docstrings as Contracts

**When:** Writing or updating a docstring.
**Rule:** If the docstring says "X is treated as Y," there must be code that enforces it (a validator, a property, or a conditional). If not, either add the enforcement or fix the docstring. Review comments repeatedly flag stale docstrings as contract violations.
