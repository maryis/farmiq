from __future__ import annotations

from contextlib import asynccontextmanager
from time import perf_counter
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import router
from app.config import settings
from app.db import SessionLocal, init_db
from app.demo import seed_demo
from app.observability import record_request, render_prometheus


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.seed_demo:
        async with SessionLocal() as session:
            await seed_demo(session)
    yield


app = FastAPI(
    title="FarmIQ API",
    version="0.1.0",
    description="FeedIQ, HealthIQ and Ask-IQ production-oriented MVP",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.middleware("http")
async def operational_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    start = perf_counter()
    response = await call_next(request)
    duration = perf_counter() - start
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    record_request(request.method, path, response.status_code, duration)
    response.headers["x-request-id"] = request_id
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["x-frame-options"] = "DENY"
    response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
    response.headers["permissions-policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def metrics():
    return render_prometheus()


@app.get("/healthz")
async def healthz():
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}
