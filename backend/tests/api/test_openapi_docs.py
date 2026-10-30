"""Guard: every route in the OpenAPI document stays fully documented."""

from typing import Any

import pytest

from app.api.docs import OPS
from app.core.config import Settings
from app.main import create_app

# Routes that are genuinely public (no credentials), keyed by operationId.
PUBLIC = {
    "auth_status",
    "auth_setup",
    "auth_local_login",
    "auth_login",
    "auth_callback",
    "auth_logout",
    "healthz",
    "readyz",
}
SCHEMES = {"ApiKeyAuth", "BearerAuth", "SessionCookie"}


@pytest.fixture
def doc(settings: Settings) -> dict[str, Any]:
    return create_app(settings).openapi()  # type: ignore[no-any-return]


def _ops(doc: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (f"{m.upper()} {p}", op)
        for p, item in doc["paths"].items()
        for m, op in item.items()
        if m in ("get", "put", "post", "delete", "patch", "head")
    ]


def test_every_operation_is_documented(doc: dict[str, Any]) -> None:
    problems: list[str] = []
    for where, op in _ops(doc):
        for key in ("summary", "description", "tags"):
            if not op.get(key):
                problems.append(f"{where}: missing {key}")
        for code, resp in op["responses"].items():
            if code[0] in "45" and not resp.get("content"):
                problems.append(f"{where}: {code} has no schema")
        if op["operationId"] not in PUBLIC and not op.get("security"):
            problems.append(f"{where}: no security")
        if op["operationId"] in PUBLIC and op.get("security"):
            problems.append(f"{where}: stale PUBLIC entry")
        if op["operationId"] not in OPS:
            problems.append(f"{where}: {op['operationId']} missing from api.docs.OPS")
    assert not problems, "\n".join(problems)


def test_operation_ids_unique_and_table_current(doc: dict[str, Any]) -> None:
    ids = [op["operationId"] for _, op in _ops(doc)]
    assert len(ids) == len(set(ids))
    assert set(OPS) <= set(ids), f"stale OPS entries: {sorted(set(OPS) - set(ids))}"


def test_every_schema_property_is_described(doc: dict[str, Any]) -> None:
    missing = [
        f"{name}.{prop}"
        for name, schema in doc["components"]["schemas"].items()
        for prop, v in schema.get("properties", {}).items()
        if not v.get("description")
    ]
    assert not missing, "\n".join(missing)


def test_security_schemes_and_tags(doc: dict[str, Any]) -> None:
    assert SCHEMES <= set(doc["components"]["securitySchemes"])
    declared = {t["name"] for t in doc["tags"] if t.get("description")}
    used = {t for _, op in _ops(doc) for t in op["tags"]}
    assert used <= declared, f"tags without description: {sorted(used - declared)}"
    assert {"ops"} <= used


def test_metrics_documents_scope_and_text(doc: dict[str, Any]) -> None:
    op = doc["paths"]["/metrics"]["get"]
    assert "metrics:read" in op["description"]
    assert "text/plain" in op["responses"]["200"]["content"]
