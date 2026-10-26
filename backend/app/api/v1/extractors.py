from fastapi import APIRouter, Depends

from app.auth.authz import require_scope
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.core.extractors import list_extractors
from app.schemas.extractors import ExtractorList

router = APIRouter(prefix="/extractors", tags=["extractors"])


@router.get("", response_model=ExtractorList)
async def get_extractors(
    p: Principal = Depends(current_principal),
) -> ExtractorList:
    require_scope(p, "sources:read")
    return ExtractorList(items=list(list_extractors()))
