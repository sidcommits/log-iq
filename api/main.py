# api/main.py
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from anthropic import AsyncAnthropic
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from openai import AsyncOpenAI
from prometheus_fastapi_instrumentator import Instrumentator

from api.routes.analyze import router as analyze_router
from api.routes.anomalies import router as anomalies_router
from api.routes.correlate import router as correlate_router
from api.routes.health import router as health_router
from api.routes.search import router as search_router
from api.routes.tasks import router as tasks_router
from db.postgres import init_pool
from db.qdrant import ensure_collection, init_qdrant
from ingestion.pipeline import IngestionWorker
from sync.engine import SyncEngine

_config: dict = yaml.safe_load(
    (Path(__file__).parent.parent / "config.yaml").read_text()
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.config = _config
    app.state.db_pool = await init_pool(dsn=_config["database"]["url"])

    qdrant_cfg = _config["qdrant"]
    app.state.qdrant_client = await init_qdrant(
        host=qdrant_cfg["host"], port=qdrant_cfg["port"]
    )
    await ensure_collection(app.state.qdrant_client, qdrant_cfg.get("collection", "log_events"))

    app.state.openai_client = AsyncOpenAI()
    app.state.anthropic_client = AsyncAnthropic()

    engine = SyncEngine(config=_config, pool=app.state.db_pool)
    await engine.start()

    ingestion_worker = IngestionWorker(
        pool=app.state.db_pool,
        openai_client=app.state.openai_client,
        qdrant_client=app.state.qdrant_client,
        batch_size=_config["ingestion"].get("batch_size", 100),
        collection=qdrant_cfg.get("collection", "log_events"),
        anomaly_config=_config.get("anomaly", {}),
    )
    await ingestion_worker.start()

    yield

    await ingestion_worker.stop()
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
app.include_router(search_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(correlate_router, prefix="/api")
app.include_router(anomalies_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
