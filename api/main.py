import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_fastapi_instrumentator import Instrumentator

from api.routes.health import router as health_router

app = FastAPI(title="LogIQ", version="0.1.0")


@app.middleware("http")
async def add_request_id(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.include_router(health_router, prefix="/api")
