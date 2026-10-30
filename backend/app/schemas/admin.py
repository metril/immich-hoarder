from pydantic import BaseModel, Field


class BackupOut(BaseModel):
    file: str = Field(
        description="File name of the new backup.", examples=["backup-20260101T000000Z.db"]
    )


class BackupInfo(BaseModel):
    file: str = Field(description="Backup file name.", examples=["backup-20260101T000000Z.db"])
    size: int = Field(description="Size in bytes.", examples=[1048576])
    mtime: str = Field(
        description="Last-modified time (ISO 8601, UTC).", examples=["2026-01-01T00:00:00Z"]
    )


class BackupList(BaseModel):
    items: list[BackupInfo] = Field(description="Backups, newest first.")
    restore_pending: bool = Field(
        default=False,
        description="True when a restore is staged and will replace the database at next startup.",
        examples=[False],
    )


class RestoreOut(BaseModel):
    restart_required: bool = Field(
        default=True,
        description="The staged backup only takes effect after the app restarts.",
        examples=[True],
    )
    restarting: bool = Field(
        default=False,
        description="True when a graceful shutdown was scheduled (restart=true was requested).",
        examples=[False],
    )


class PruneOut(BaseModel):
    jobs: int = Field(description="Old finished jobs deleted.", examples=[12])
    ephemeral_sources: int = Field(description="Finished ephemeral sources deleted.", examples=[3])


class ImportResult(BaseModel):
    created: dict[str, int] = Field(
        description="Rows created, per resource type.", examples=[{"targets": 1, "sources": 2}]
    )
    skipped: dict[str, int] = Field(
        description="Rows skipped because they already exist, per resource type.",
        examples=[{"credentials": 1}],
    )
    errors: list[str] = Field(
        description="Problems found in the document; non-empty means nothing was applied.",
        examples=[["sources[0]: unknown target 'main'"]],
    )
    applied: bool = Field(
        description="False for a dry run or when errors prevented applying.", examples=[True]
    )
