from fastapi import APIRouter

from app.api.v1 import apikeys, credentials, settings, sources, targets, users

api_router = APIRouter(prefix="/api/v1")
for _m in (targets, credentials, sources, apikeys, users, settings):
    api_router.include_router(_m.router)
