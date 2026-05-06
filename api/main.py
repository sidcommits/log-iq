import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_fastapi_instrumentator import Instrumentator

from api.routes.health import router as health_router
from db.postgres import init_pool
from sync.engine import SyncEngine

_config: dict = yaml.safe_load(
    (Path(__file__).parent.parent / "config.yaml").read_text()
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await init_pool(dsn=_config["database"]["url"])
    engine = SyncEngine(config=_config, pool=app.state.db_pool)
    await engine.start()
    yield
    await engine.stop()
    await app.state.db_pool.close()


app = FastAPI(title="LogIQ", version="0.1.0", lifespan=lifespan)


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
