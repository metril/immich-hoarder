from fastapi import APIRouter, Depends

from app.auth.authz import require_scope
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.core.extractors import ExtractorInfo, list_extractors

router = APIRouter(prefix="/extractors", tags=["extractors"])


@router.get("")
async def get_extractors(
    p: Principal = Depends(current_principal),
) -> dict[str, list[ExtractorInfo]]:
    require_scope(p, "sources:read")
    return {"items": list(list_extractors())}
