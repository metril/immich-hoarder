from fastapi import APIRouter

from app.api.v1 import (
    apikeys,
    credentials,
    extractors,
    jobs,
    settings,
    sources,
    streams,
    targets,
    users,
)

api_router = APIRouter(prefix="/api/v1")
for _m in (targets, credentials, sources, apikeys, users, settings, extractors, streams, jobs):
    api_router.include_router(_m.router)
