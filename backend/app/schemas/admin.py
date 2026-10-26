from pydantic import BaseModel


class BackupOut(BaseModel):
    file: str


class BackupInfo(BaseModel):
    file: str
    size: int
    mtime: str


class BackupList(BaseModel):
    items: list[BackupInfo]


class PruneOut(BaseModel):
    jobs: int
    ephemeral_sources: int


class ImportResult(BaseModel):
    created: dict[str, int]
    skipped: dict[str, int]
    errors: list[str]
    applied: bool
