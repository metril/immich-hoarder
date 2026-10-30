from pydantic import BaseModel, Field

from app.core.extractors import ExtractorInfo


class ExtractorList(BaseModel):
    items: list[ExtractorInfo] = Field(description="Supported extractors (sites).")
