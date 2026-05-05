from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "dependencies": {
            "loki":       {"status": "not_configured"},
            "qdrant":     {"status": "not_configured"},
            "postgresql": {"status": "not_configured"},
            "openai":     {"status": "not_configured"},
            "claude":     {"status": "not_configured"},
        },
        "version": "0.1.0",
    }
