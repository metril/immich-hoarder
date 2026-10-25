from fastapi import APIRouter

from app.api.v1 import apikeys, credentials, extractors, settings, sources, targets, users

api_router = APIRouter(prefix="/api/v1")
for _m in (targets, credentials, sources, apikeys, users, settings, extractors):
    api_router.include_router(_m.router)
