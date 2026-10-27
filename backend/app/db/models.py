import enum
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Role(enum.StrEnum):
    admin = "admin"
    user = "user"


class Visibility(enum.StrEnum):
    private = "private"
    everyone = "everyone"
    restricted = "restricted"


class Perm(enum.StrEnum):
    use = "use"
    edit = "edit"


class PrincipalType(enum.StrEnum):
    user = "user"
    group = "group"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class CredentialKind(enum.StrEnum):
    oauth = "oauth"
    cookies = "cookies"
    userpass = "userpass"
    token = "token"
    apprise = "apprise"


class BackfillMode(enum.StrEnum):
    full = "full"
    last_n = "last_n"
    since = "since"


def _enum(e: type[enum.Enum]) -> SAEnum:
    return SAEnum(
        e,
        native_enum=False,
        create_constraint=False,
        length=16,
        values_callable=lambda x: [m.value for m in x],
    )


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Ownable:
    share_type: ClassVar[str]
    id: Mapped[int]
    visibility: Mapped[Visibility] = mapped_column(
        _enum(Visibility), default=Visibility.private, server_default=Visibility.private.value
    )

    @declared_attr
    def owner_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)


class User(Timestamps, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role), default=Role.user)
    groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    session_gen: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Share(Timestamps, Base):
    __tablename__ = "shares"
    __table_args__ = (
        UniqueConstraint(
            "resource_type", "resource_id", "principal_type", "principal_id", name="uq_shares"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[int] = mapped_column(Integer)
    principal_type: Mapped[PrincipalType] = mapped_column(_enum(PrincipalType))
    principal_id: Mapped[str] = mapped_column(String(255))
    perm: Mapped[Perm] = mapped_column(_enum(Perm))


class ApiKey(Timestamps, Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    # String(8) is intentional: the 8-char lowercase-alphanumeric lookup prefix of the raw key
    prefix: Mapped[str] = mapped_column(String(8), unique=True)
    hash: Mapped[str] = mapped_column(String(255))
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class ImmichTarget(Ownable, Timestamps, Base):
    share_type = "target"
    __tablename__ = "immich_targets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(2048))
    api_key_enc: Mapped[bytes] = mapped_column(LargeBinary)


class Credential(Ownable, Timestamps, Base):
    share_type = "credential"
    __tablename__ = "credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    site: Mapped[str] = mapped_column(String(255))
    kind: Mapped[CredentialKind] = mapped_column(_enum(CredentialKind))
    secret_enc: Mapped[bytes] = mapped_column(LargeBinary)


class Source(Ownable, Timestamps, Base):
    share_type = "source"
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(2048))
    extractor: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[int] = mapped_column(
        ForeignKey("immich_targets.id", ondelete="RESTRICT"), index=True
    )
    credential_id: Mapped[int | None] = mapped_column(
        ForeignKey("credentials.id", ondelete="RESTRICT"), index=True
    )
    album_template: Mapped[str] = mapped_column(String(512), default="")
    schedule_cron: Mapped[str | None] = mapped_column(String(64))
    backfill_mode: Mapped[BackfillMode] = mapped_column(
        _enum(BackfillMode), default=BackfillMode.full
    )
    backfill_value: Mapped[str | None] = mapped_column(String(64))
    allow_animated: Mapped[bool] = mapped_column(Boolean, default=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notify: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    gdl_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    proxy: Mapped[str | None] = mapped_column(String(2048))
    log_level: Mapped[str | None] = mapped_column(String(16))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    ephemeral: Mapped[bool] = mapped_column(Boolean, default=False)


class Job(Timestamps, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index(
            "uq_jobs_active_source",
            "source_id",
            unique=True,
            sqlite_where=text("status IN ('queued','running')"),
            postgresql_where=text("status IN ('queued','running')"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    triggered_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus), default=JobStatus.queued)
    log_level: Mapped[str | None] = mapped_column(String(16))
    phase: Mapped[str | None] = mapped_column(String(16))
    counters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job_id_id", "job_id", "id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    level: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class JobItem(Base):
    __tablename__ = "job_items"
    __table_args__ = (Index("ix_job_items_job_id_id", "job_id", "id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(2048))
    outcome: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text)
    immich_asset_id: Mapped[str | None] = mapped_column(String(64))


class AssetSeen(Base):
    # Rows outlive their source (source_id -> NULL on delete): intentional, since dedupe
    # is per target via sha1 and phash, not per source.
    __tablename__ = "assets_seen"
    __table_args__ = (
        UniqueConstraint("source_id", "url_hash", name="uq_assets_seen_source_url"),
        Index("ix_assets_seen_target_sha1", "target_id", "sha1"),
        Index("ix_assets_seen_target_ph0", "target_id", "ph0"),
        Index("ix_assets_seen_target_ph1", "target_id", "ph1"),
        Index("ix_assets_seen_target_ph2", "target_id", "ph2"),
        Index("ix_assets_seen_target_ph3", "target_id", "ph3"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("immich_targets.id", ondelete="CASCADE"))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    url_hash: Mapped[bytes] = mapped_column(LargeBinary(16))
    sha1: Mapped[bytes | None] = mapped_column(LargeBinary(20))
    # signed int64 (two's complement of the unsigned 64-bit hash)
    phash: Mapped[int | None] = mapped_column(BigInteger)
    ph0: Mapped[int | None] = mapped_column(Integer)
    ph1: Mapped[int | None] = mapped_column(Integer)
    ph2: Mapped[int | None] = mapped_column(Integer)
    ph3: Mapped[int | None] = mapped_column(Integer)
    immich_asset_id: Mapped[bytes | None] = mapped_column(LargeBinary(16))
    seen_at: Mapped[int] = mapped_column(BigInteger)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
