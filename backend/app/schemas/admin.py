from pydantic import BaseModel, Field


class BackupOut(BaseModel):
    file: str


class BackupInfo(BaseModel):
    file: str
    size: int
    mtime: str


class BackupList(BaseModel):
    items: list[BackupInfo]
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
    jobs: int
    ephemeral_sources: int


class ImportResult(BaseModel):
    created: dict[str, int]
    skipped: dict[str, int]
    errors: list[str]
    applied: bool
