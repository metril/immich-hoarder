"""Picklable job inputs handed to the rip worker process."""

from typing import Any

from pydantic import BaseModel, SecretStr

from app.db.models import BackfillMode, CredentialKind
from app.rip.filters import FilterSpec


class SourceSnapshot(BaseModel):
    id: int
    name: str
    url: str
    extractor: str
    target_id: int
    album_template: str
    backfill_mode: BackfillMode
    backfill_value: str | None
    allow_animated: bool
    filters: FilterSpec
    gdl_options: dict[str, Any]
    proxy: str | None
    log_level: str


class TargetSnapshot(BaseModel):
    id: int
    url: str
    api_key: SecretStr


class CredentialSnapshot(BaseModel):
    site: str
    kind: CredentialKind
    secret: SecretStr
