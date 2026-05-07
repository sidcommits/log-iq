from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/agents")
async def list_agents() -> None:
    raise HTTPException(status_code=501, detail="agents API not available in v1.0")


@router.post("/agents/trigger")
async def trigger_agent() -> None:
    raise HTTPException(status_code=501, detail="agents API not available in v1.0")
