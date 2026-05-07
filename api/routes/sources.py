# api/routes/sources.py
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class SourceInfo(BaseModel):
    name: str
    type: str
    url: str
    mode: str


class SourcesResponse(BaseModel):
    sources: list[SourceInfo]


@router.get("/sources", response_model=SourcesResponse)
async def list_sources(request: Request) -> SourcesResponse:
    raw = request.app.state.config.get("sources", [])
    return SourcesResponse(sources=[
        SourceInfo(
            name=s["name"],
            type=s["type"],
            url=s["url"],
            mode=s.get("mode", "poll"),
        )
        for s in raw
    ])
