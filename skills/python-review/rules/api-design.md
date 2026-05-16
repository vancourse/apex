# API Design

REST conventions, response shapes, pagination, and partial-success contracts.

## REST Conventions — Nouns, Plural, Nested

**Rule:** Nouns not verbs: `/agents` not `/getAgents`. Plural nouns: `/agents` not `/agent`. Nest for relationships: `/agents/{id}/runs`.

## Standard Response Envelope

**When:** Returning a list endpoint.
**Rule:** Wrap in a paginated envelope with `data` and `meta`.

```python
class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: PaginationMeta

class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
```

## Expose the Full Domain Object — Don't Scope to the Current UI

**When:** Shaping an API response to match what the frontend renders today.
**Rule:** Return the full domain object. Do not trim fields "because the UI doesn't show them." Beautification and field selection are the frontend's job.
**Why:** A thin API forces the frontend to merge state from N endpoints, and every new UI need triggers a backend change.

## Trust the Framework's Exception Middleware

**When:** Tempted to wrap every exception in the project's HTTP error type at the route handler.
**Rule:** Let exceptions propagate. The framework's exception middleware (e.g. FastAPI's) converts them to structured HTTP responses. Only raise the project's HTTP error (e.g. `AppHTTPError`) when you need to control the status code.
**Why:** Hand-wrapping at every handler is noise; a generic unhandled exception should flow to a 500 via the middleware.

## Use 422 for "Authorized but Disallowed"

**Rule:** Reserve HTTP 403 for service-level authorization failures. If the user is authenticated and allowed to hit the endpoint but the operation is invalid given domain state (can't modify published object, can't delete referenced row), return 422.

## Don't Invent Bespoke Exception Classes for "Stuff Is Broken"

**Rule:** Domain errors deserve named exception classes. "Something unexpected went wrong" does not — a generic exception flows to a 500 via the framework. A bespoke `GenericFooError` that adds nothing over `Exception` is noise.

## Standard Error Format — Machine + Human + Traceable ID

**Rule:** Every error response includes a machine-readable `error_code`, human-readable `message`, and a UUID `error_id` for log correlation.

```python
class ErrorResponse(BaseModel):
    error_code: str      # "agent_not_found"
    message: str         # "Agent 'abc123' not found"
    error_id: str = Field(default_factory=lambda: str(uuid4()))
```

## Paginate All List Endpoints — Never Return Unbounded Results

**Rule:** Every list endpoint must paginate. Use `page` + `page_size` query params with a bounded maximum.

```python
@app.get("/agents")
async def list_agents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[Agent]: ...
```

## Define Explicit Response Shapes for Partial Success

**When:** An endpoint can partially succeed (primary operation completes, secondary side-effect fails).
**Rule:** Use a discriminated response with explicit fields for each outcome. No ambiguous `status: "success" | "error"` when partial success is possible.

```python
# ✅ GOOD
class PipelineResponse(BaseModel):
    primary_status: Literal["complete", "partial", "failed"]
    primary_data: dict | None = None
    side_effect_status: Literal["applied", "skipped", "failed"] | None = None
    error_detail: str | None = None
```

## Request Validation — `extra="forbid"` + `min_length`

**When:** Defining a request `BaseModel`.
**Rule:** Set `model_config = ConfigDict(extra="forbid")`. Required string fields get `Field(min_length=1)`.
**See also:** `rules/types-and-models.md` for the full Pydantic model rules.

## PATCH Payloads — Default `None`, Not `""`

**When:** Defining an update payload with optional fields.
**Rule:** Every optional field defaults to `None`. The handler skips `None` fields during update. Default `""` silently overwrites on every partial request.
**See also:** `rules/types-and-models.md`.

## Reject No-Op Update Requests

**When:** An update payload has all optional fields.
**Rule:** Add a `model_validator(mode="after")` requiring at least one non-identifier field to be set.
**See also:** `rules/types-and-models.md`.

## Warn When Silently Stripping Deprecated Fields

**When:** A backward-compat validator strips deprecated fields from API input.
**Rule:** Emit a warning log when stripping happens. Silent stripping is correct for persisted data migration, wrong for live requests.
**See also:** `rules/types-and-models.md`.
