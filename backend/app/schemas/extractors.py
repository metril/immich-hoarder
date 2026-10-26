from pydantic import BaseModel

from app.core.extractors import ExtractorInfo


class ExtractorList(BaseModel):
    items: list[ExtractorInfo]
