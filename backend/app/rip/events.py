"""Event payloads emitted by the rip pipeline (consumed by the job runner)."""

from collections.abc import Callable
from typing import Any, NotRequired, TypedDict

Emit = Callable[[dict[str, Any]], None]


class PhaseEvent(TypedDict):
    type: str  # "phase"
    name: str  # starting | extracting | draining | done


class ItemEvent(TypedDict):
    # type: item.discovered | item.downloaded | item.filtered | item.duplicate |
    #       item.linked | item.uploaded | item.failed | item.deleted_in_immich
    type: str
    url: str
    reason: NotRequired[str]
    immich_asset_id: NotRequired[str]
    size: NotRequired[int]


class ProgressEvent(TypedDict):
    type: str  # "progress"
    counters: dict[str, int]
    bytes: int
    rate_bps: float
    scratch_bytes: int
    scratch_free_ratio: float


class LogEvent(TypedDict):
    type: str  # "log"
    level: str
    msg: str
    logger: str
