"""OpenAPI documentation: app description, tags, shared error models and per-route docs.

Routes keep their behaviour in the route modules; the human-facing summary, description,
required access and extra error responses live in ``OPS`` (keyed by operation id) and are
merged into the generated schema by ``install``. ``tests/api/test_openapi_docs.py`` fails
when a route is added without an entry.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

DESCRIPTION = """\
Self-hosted service that rips galleries with gallery-dl and uploads them to Immich.

## Authentication

Send one of the following on every request (the **Authorize** button above accepts the first two):

* **API key** in the `X-API-Key` header, or as `Authorization: Bearer ih_...`. Keys are created
  under `/api/v1/api-keys` and are limited to the scopes they were granted.
* **OIDC access token** (a JWT from the configured identity provider) as `Authorization: Bearer <jwt>`.
  Tokens are not scope-limited; the user's role and resource permissions apply.
* **Session cookie** (`session`), set by `/api/v1/auth/login` (OIDC) or `/api/v1/auth/local/login`.
  Unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`) must also send the `ih_csrf` cookie value in the
  `X-CSRF-Token` header, otherwise the request fails with 403. API keys and bearer tokens need no CSRF header.

## Scopes

An API key carries a list of scopes. A route lists the scope it needs in its description.
Scopes are `<resource>:read|write` for `sources`, `targets`, `credentials`, `jobs`, `keys`,
`settings` and `users`, plus `sources:run`, `metrics:read` and `admin` (every admin route).
`settings:*` and `users:*` are only usable by admin users. Sessions and OIDC tokens are not scope-limited.

## Pagination, search and sorting

List endpoints return `{"items": [...], "next_cursor": "..."}`. Pass `limit` (1-200, default 50) and
the previous response's `next_cursor` as `cursor` to continue; `next_cursor` is null on the last page.
Cursors are opaque and only valid with the `sort` they were issued for (otherwise 400).
Where supported, `sort` picks the order (a leading `-` means descending) and `q` filters by
case-insensitive substring.

## Errors

Errors are JSON `{"detail": "message"}` with the matching HTTP status. A 422 is either a request
validation failure, `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`, or a rule violation with a
string detail such as `{"detail": "invalid cursor"}`. A few errors carry extra context in `detail`
(for example a 409 with the id of the already-active job). Rate-limited calls return 429, with
`Retry-After` on login.

## Server-sent events

`GET /api/v1/jobs/{job_id}/stream` and `GET /api/v1/jobs/stream` return `text/event-stream`.
Each SSE message has an `event:` name and a JSON `data:` object. Event types: `log` and `phase` (job
log lines and phase changes), `progress` (`counters`), `status` (`job_id`, `status`), `item.<outcome>`
(per-item results, `url`, `reason`, `immich_asset_id`), `gap` (events were dropped; refetch state) and
`end` (the stream is complete). A comment ping is sent every 15 seconds. The per-job stream first
replays recent events and items; the dashboard stream carries only `status`, `progress`, `phase` and
`gap` for jobs the caller may see.
"""

TAGS: list[dict[str, str]] = [
    {"name": "auth", "description": "Sign-in, first-run setup and the current user."},
    {"name": "targets", "description": "Immich servers that ripped media is uploaded to."},
    {"name": "credentials", "description": "Site logins and notification URLs, stored encrypted."},
    {
        "name": "sources",
        "description": "Gallery URLs to rip, with schedule, filters and notifications.",
    },
    {
        "name": "jobs",
        "description": "Rip runs: start, inspect, cancel, retry and live progress streams.",
    },
    {"name": "uploads", "description": "Assets uploaded to Immich and their thumbnails."},
    {"name": "api-keys", "description": "Scoped API keys for automation."},
    {"name": "users", "description": "User directory and local account management (admin)."},
    {
        "name": "settings",
        "description": "Instance settings: ripping, runtime, notifications and sign-in (admin).",
    },
    {"name": "extractors", "description": "Sites supported by the ripper."},
    {
        "name": "admin",
        "description": "Backups, restore, config export/import and maintenance (admin).",
    },
    {"name": "ops", "description": "Health, readiness and Prometheus metrics for operators."},
]


class ErrorResponse(BaseModel):
    """Body of every non-validation error."""

    detail: str | dict[str, Any] = Field(
        description="Human-readable message, or an object with extra context for some conflicts.",
        examples=["not found"],
    )


class ValidationIssue(BaseModel):
    loc: list[str | int] = Field(
        description="Path to the offending field, starting with body, query or path.",
        examples=[["body", "name"]],
    )
    msg: str = Field(description="What is wrong.", examples=["Field required"])
    type: str = Field(description="Machine-readable error type.", examples=["missing"])


class ValidationErrorResponse(BaseModel):
    """Body of a 422 caused by request validation (other 422s use ErrorResponse)."""

    detail: list[ValidationIssue] = Field(description="One entry per invalid field.")


class HealthOut(BaseModel):
    status: str = Field(description="Always `ok`.", examples=["ok"])


class NotReadyOut(BaseModel):
    status: str = Field(description="Always `unavailable`.", examples=["unavailable"])
    failing: list[str] = Field(
        description="Components that are down: db, scheduler, supervisor, writer or bridge.",
        examples=[["db"]],
    )


class Op:
    """Docs for one operation. `scope` is an access rule, see `access_text`."""

    def __init__(
        self,
        summary: str,
        description: str | None = None,
        access: str = "any",
        errors: dict[int, str] | None = None,
        sse: str | None = None,
    ) -> None:
        self.summary = summary
        self.description = description
        self.access = access
        self.errors = errors or {}
        self.sse = sse


def operation_id(route: APIRoute) -> str:
    return f"auth_{route.name}" if "auth" in route.tags else route.name


_RW = "read", "write"


def access_text(access: str) -> str:
    if access == "public":
        return "**Access:** public; no authentication required."
    if access == "any":
        return "**Access:** any authenticated caller; no scope needed."
    if access == "admin":
        return "**Access:** admin users only. API keys need the `admin` scope."
    if access.startswith("admin+"):
        s = access[6:]
        return f"**Access:** admin users only. API keys need the `{s}` or `admin` scope."
    return (
        f"**Access:** API keys need the `{access}` scope (admin keys pass); sessions and OIDC "
        "tokens are not scope-limited. Resource permissions still apply."
    )


def _scope_in(access: str) -> str | None:
    if access in ("public", "any"):
        return None
    return access[6:] if access.startswith("admin+") else access


def _shares(resource: str, noun: str) -> dict[str, Op]:
    return {
        f"get_{resource}_shares": Op(
            f"Get {noun} sharing",
            f"Returns the {noun}'s visibility and its explicit user and group grants.",
            f"{resource}:read",
        ),
        f"put_{resource}_shares": Op(
            f"Set {noun} sharing",
            f"Replaces the {noun}'s visibility and grants. Only the owner or an admin may change "
            "sharing. Unknown users are rejected with 422.",
            f"{resource}:write",
            {422: "Unknown user, or validation error"},
        ),
    }


_ID = "Id of the resource."

OPS: dict[str, Op] = {
    # auth
    "auth_status": Op(
        "Get sign-in status",
        "Tells the sign-in page which methods are available and whether first-run setup is open.",
        "public",
    ),
    "auth_setup": Op(
        "Create the first admin",
        "Creates the first local admin and signs them in. Only available while no admin exists "
        "(or in break-glass reset mode with the one-time reset token).",
        "public",
        {403: "Invalid reset token", 409: "Already set up"},
    ),
    "auth_local_login": Op(
        "Sign in with a password",
        "Signs in a local account and sets the `session` and `ih_csrf` cookies. Failed attempts "
        "are rate limited per client; the 429 carries `Retry-After`.",
        "public",
        {401: "Invalid credentials", 404: "Local sign-in is disabled", 429: "Too many attempts"},
    ),
    "auth_login": Op(
        "Start OIDC sign-in",
        "Redirects the browser to the identity provider. Returns 204 when called with an Accept "
        "header that is not HTML, so clients can probe whether OIDC is available.",
        "public",
        {503: "OIDC is not configured"},
    ),
    "auth_callback": Op(
        "Finish OIDC sign-in",
        "OIDC redirect target: exchanges the code, creates the session and redirects to `/`.",
        "public",
        {
            401: "Login failed",
            403: "The user's groups do not grant access",
            503: "OIDC is not configured",
        },
    ),
    "auth_logout": Op(
        "Sign out",
        "Clears the session. Safe to call when not signed in.",
        "public",
    ),
    "auth_me": Op(
        "Get the current user",
        "Returns the authenticated user, their role and groups. Also issues the CSRF cookie "
        "for session callers.",
    ),
    "auth_change_own_password": Op("Change your own password", None),
    # targets
    "list_targets": Op("List targets", None, "targets:read"),
    "create_target": Op(
        "Create a target",
        "Registers an Immich server. The API key is stored encrypted and never returned.",
        "targets:write",
    ),
    "get_target": Op("Get a target", "Returns one target the caller may see.", "targets:read"),
    "patch_target": Op(
        "Update a target",
        "Changes the given fields. Sending `api_key` replaces the stored key.",
        "targets:write",
        {403: "The caller may use but not edit the target"},
    ),
    "delete_target": Op(
        "Delete a target",
        "Deletes the target and its sharing. Refused while a source still uses it.",
        "targets:write",
        {409: "The target is in use by a source"},
    ),
    "test_target": Op(
        "Test a target",
        "Connects to the Immich server and reports its version and any missing API-key permissions.",
        "targets:read",
    ),
    "target_albums": Op(
        "List target albums",
        "Lists the albums on the Immich server, for choosing an album template.",
        "targets:read",
        {502: "Immich is unreachable or rejected the API key"},
    ),
    "thumbnail": Op(
        "Get an asset thumbnail",
        "Proxies a thumbnail or preview image for an asset this app uploaded to the target. "
        "Responds with the image bytes.",
        "targets:read",
        {422: "Invalid asset id", 502: "Immich is unreachable or rejected the API key"},
    ),
    **_shares("targets", "target"),
    # credentials
    "list_credentials": Op("List credentials", None, "credentials:read"),
    "create_credential": Op(
        "Create a credential",
        "Stores a site login or notification URL. The secret is encrypted and never returned. "
        "`apprise` credentials are validated.",
        "credentials:write",
    ),
    "get_credential": Op(
        "Get a credential", "Returns one credential (without its secret).", "credentials:read"
    ),
    "patch_credential": Op(
        "Update a credential",
        "Changes the given fields. Sending `secret` replaces the stored secret.",
        "credentials:write",
        {403: "The caller may use but not edit the credential"},
    ),
    "delete_credential": Op(
        "Delete a credential",
        "Deletes the credential and its sharing. Refused while a source still uses it.",
        "credentials:write",
        {409: "The credential is in use by a source"},
    ),
    **_shares("credentials", "credential"),
    # sources
    "list_sources": Op("List sources", None, "sources:read"),
    "create_source": Op(
        "Create a source",
        "Creates a source and registers its schedule. The extractor is detected from the URL; "
        "unsupported URLs, unknown cron or template fields, and unusable targets or credentials "
        "are rejected with 422.",
        "sources:write",
    ),
    "preview_source": Op(
        "Preview a source",
        "Dry-runs a source definition without saving it and lists the first items it would fetch, "
        "with the filter verdict for each. Runs gallery-dl in a sandboxed subprocess and is rate limited.",
        "sources:read",
        {429: "Too many previews running", 502: "The preview failed", 504: "The preview timed out"},
    ),
    "get_source": Op("Get a source", "Returns one source the caller may see.", "sources:read"),
    "patch_source": Op(
        "Update a source",
        "Changes the given fields; omitted fields are kept and required fields cannot be set to null.",
        "sources:write",
        {403: "The caller may use but not edit the source"},
    ),
    "delete_source": Op(
        "Delete a source",
        "Deletes the source, its job history and its sharing.",
        "sources:write",
        {409: "The source has an active job"},
    ),
    "forget_seen": Op(
        "Forget seen items",
        "Clears the source's memory of already-seen items so the next run re-evaluates everything.",
        "sources:write",
        {409: "The source has an active job"},
    ),
    **_shares("sources", "source"),
    # jobs
    "run_source": Op(
        "Run a source",
        "Queues a job for the source. Responds 202 with the queued job; follow it with the job "
        "endpoints or the SSE stream.",
        "sources:run",
        {
            409: "A job is already active for the source (`detail.job_id` names it)",
            503: "The job runtime is unavailable",
        },
    ),
    "adhoc_rip": Op(
        "Run an ad-hoc rip",
        "Creates an ephemeral source from the body (a source payload; schedule is ignored) and "
        "queues a job for it. The source is cleaned up after the run.",
        "sources:run",
        {503: "The job runtime is unavailable"},
    ),
    "list_jobs": Op("List jobs", None, "jobs:read"),
    "get_job": Op("Get a job", "Returns one job with its counters and status.", "jobs:read"),
    "job_items": Op(
        "List job items",
        "Pages through the per-item outcomes of a job, oldest first.",
        "jobs:read",
    ),
    "job_events": Op(
        "List job events",
        "Pages through a job's log and phase events, oldest first. `min_level` hides lower severities.",
        "jobs:read",
        {422: "Invalid min_level"},
    ),
    "cancel_job": Op(
        "Cancel a job",
        "Asks a queued or running job to stop. Responds 202 with the job.",
        "jobs:write",
        {409: "The job is not active"},
    ),
    "retry_job": Op(
        "Retry a job",
        "Queues a new job for the same source. Responds 202 with the new job.",
        "sources:run",
        {409: "A job is already active for the source", 503: "The job runtime is unavailable"},
    ),
    "delete_job": Op("Delete a job", None, "jobs:write"),
    "stream_job": Op(
        "Stream one job",
        "Server-sent events for one job: replays recent events and items, then streams live "
        "until the job ends. Each user may hold a limited number of streams.",
        "jobs:read",
        {429: "Too many open streams", 503: "The job runtime is unavailable"},
        sse="job",
    ),
    "dashboard": Op(
        "Stream all jobs",
        "Server-sent events with status, phase and progress changes for every job the caller "
        "may see. Each user may hold a limited number of streams.",
        "jobs:read",
        {429: "Too many open streams", 503: "The job runtime is unavailable"},
        sse="dashboard",
    ),
    # uploads
    "list_uploads": Op(
        "List uploads",
        "Pages through assets that were uploaded to Immich, newest first. Filter with `source_id` "
        "and `target_id`.",
        "jobs:read",
    ),
    # extractors
    "get_extractors": Op(
        "List extractors",
        "Lists the sites the ripper supports, with an example URL for each.",
        "sources:read",
    ),
    # api keys
    "list_keys": Op("List API keys", None, "keys:read"),
    "create_key": Op("Create an API key", None, "keys:write"),
    "get_key": Op("Get an API key", None, "keys:read"),
    "update_key": Op("Update an API key", None, "keys:write"),
    "rotate_key": Op("Rotate an API key", None, "keys:write"),
    "revoke_key": Op("Revoke an API key", None, "keys:write"),
    # users
    "list_users": Op("List users", None, "admin+users:read"),
    "user_directory": Op(
        "Search the user directory",
        "Looks up enabled users by name for the sharing picker. Returns ids and display names only; "
        "`q` must be at least 2 characters.",
    ),
    "create_local_user": Op("Create a local user", None, "admin+users:write"),
    "reset_password": Op("Reset a user's password", None, "admin+users:write"),
    "delete_user": Op("Delete a local user", None, "admin+users:write"),
    "patch_user": Op("Update a user", None, "admin+users:write"),
    # settings
    "get_settings": Op("Get settings", None, "admin+settings:read"),
    "put_settings": Op("Update settings", None, "admin+settings:write"),
    "test_oidc": Op("Test the OIDC configuration", None, "admin+settings:write"),
    "set_local_admin_password": Op("Set the local admin password", None, "admin+settings:write"),
    # admin
    "create_backup": Op(
        "Create a backup",
        "Writes a consistent snapshot of the SQLite database to the backup directory.",
        "admin",
        {
            409: "Backups are not supported for this database",
            500: "The backup failed",
            507: "Not enough space",
        },
    ),
    "get_backups": Op("List backups", None, "admin"),
    "download_backup": Op("Download a backup", None, "admin"),
    "delete_backup": Op("Delete a backup", None, "admin"),
    "restore_backup": Op("Stage a restore", None, "admin"),
    "cancel_restore": Op("Cancel a staged restore", None, "admin"),
    "run_prune": Op(
        "Prune old data",
        "Deletes finished jobs and ephemeral sources that are past their retention and reports the counts.",
        "admin",
    ),
    "export_yaml": Op(
        "Export configuration",
        "Exports targets, credentials and sources as YAML. `secrets=omit` leaves secrets out; "
        "`secrets=encrypted` includes them encrypted with the instance master key. The export is audit-logged.",
        "admin",
    ),
    "import_yaml": Op(
        "Import configuration",
        "Imports a YAML document produced by the export (request body is the raw YAML, limited in "
        "size). Existing rows are skipped; any validation error aborts the whole import.",
        "admin",
        {413: "The body is too large", 422: "Invalid YAML, wrong structure or unsupported version"},
    ),
    # ops
    "healthz": Op(
        "Liveness probe",
        "Returns 200 while the process is serving requests. Used by container health checks.",
        "public",
    ),
    "readyz": Op(
        "Readiness probe",
        "Checks the database and the background components (scheduler, supervisor, writer, bridge). "
        "Returns 503 listing whatever is down.",
        "public",
        {503: "A component is not ready (`failing` lists them)"},
    ),
    "metrics": Op(
        "Prometheus metrics",
        "Metrics in the Prometheus text exposition format. API keys need the `metrics:read` scope; "
        "sessions and OIDC tokens must belong to an admin.",
        "metrics:read",
    ),
}

_PLAIN = {"type": "string"}
_SSE_EXAMPLE = {
    "job": (
        "Events: `log`, `phase`, `item.<outcome>`, `progress`, `status`, `gap`, then `end`. "
        "Each `data:` is a JSON object with a `type`; `status` events carry `job_id` and `status`, "
        "`progress` events carry `counters`, item events carry `url`, `reason` and `immich_asset_id`."
    ),
    "dashboard": (
        "Events: `status` (`job_id`, `status`), `phase`, `progress` (`job_id`, `counters`) and `gap` "
        "when events were dropped and the client should refetch."
    ),
}
_EXAMPLES = {
    "job": 'event: progress\ndata: {"type":"progress","counters":{"seen":40,"uploaded":12}}\n\n'
    'event: status\ndata: {"type":"status","job_id":17,"status":"succeeded"}\n\n'
    "event: end\ndata: {}\n",
    "dashboard": 'event: status\ndata: {"type":"status","job_id":17,"status":"running"}\n',
}

_AUTH_ERRORS = {
    401: "Missing, invalid, expired or revoked credentials",
    403: "The credentials lack the required scope or role, or the CSRF token is missing or invalid",
}
_FILE_200 = {
    "download_backup": ("application/octet-stream", {"type": "string", "format": "binary"}),
    "export_yaml": ("application/yaml", _PLAIN),
    "thumbnail": ("image/*", {"type": "string", "format": "binary"}),
    "metrics": ("text/plain", _PLAIN),
}


def _model_ref(components: dict[str, Any], model: type[BaseModel]) -> dict[str, str]:
    name = model.__name__
    if name not in components:
        js = model.model_json_schema(ref_template="#/components/schemas/{model}")
        for dname, dschema in js.pop("$defs", {}).items():
            components.setdefault(dname, dschema)
        components[name] = js
    return {"$ref": f"#/components/schemas/{name}"}


def _error_content(components: dict[str, Any], model: type[BaseModel]) -> dict[str, Any]:
    return {"application/json": {"schema": _model_ref(components, model)}}


def enrich(schema: dict[str, Any]) -> None:
    """Merge OPS docs, error bodies and non-JSON success responses into a generated schema."""
    comps = schema.setdefault("components", {}).setdefault("schemas", {})
    err = _error_content(comps, ErrorResponse)
    verr = {
        "application/json": {
            "schema": {
                "anyOf": [
                    _model_ref(comps, ValidationErrorResponse),
                    _model_ref(comps, ErrorResponse),
                ]
            }
        }
    }
    for path, item in schema["paths"].items():
        for op in item.values():
            doc = OPS.get(op["operationId"])
            if doc is None:
                continue
            if doc.description is not None:  # fully documented here; else keep the route's own
                op["summary"] = doc.summary
            base = doc.description or op.get("description") or ""
            note = access_text(doc.access)
            sc = _scope_in(doc.access)
            has = sc is not None and f"`{sc}`" in base
            op["description"] = base if has else f"{base}\n\n{note}".strip()
            responses = op.setdefault("responses", {})
            wanted = dict(doc.errors)
            if doc.access != "public":
                for code, text in _AUTH_ERRORS.items():
                    wanted.setdefault(code, text)
            if "{" in path:
                wanted.setdefault(404, "Not found, or not visible to the caller")
            for code, text in wanted.items():
                responses.setdefault(str(code), {"description": text})
            for code, resp in responses.items():
                if code == "422":
                    resp["description"] = resp.get("description") or "Validation error"
                    resp["content"] = verr
                elif code[0] in "45" and "content" not in resp:
                    resp["content"] = err
            if doc.sse:
                ok = responses["200"]
                ok["description"] = _SSE_EXAMPLE[doc.sse]
                ok["content"] = {
                    "text/event-stream": {"schema": _PLAIN, "example": _EXAMPLES[doc.sse]}
                }
            elif op["operationId"] in _FILE_200:
                mt, sch = _FILE_200[op["operationId"]]
                ok = responses["200"]
                ok["content"] = {mt: {"schema": sch}}
    for name in ("HTTPValidationError", "ValidationError"):
        comps.pop(name, None)


def install(app: FastAPI) -> None:
    """Replace app.openapi with a version that applies `enrich` once."""
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            enrich(original())
        return app.openapi_schema  # type: ignore[return-value]

    app.openapi = openapi  # type: ignore[method-assign]
