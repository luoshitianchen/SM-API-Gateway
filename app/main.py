from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

VERSION = "1.1.0"
SERVICE_NAME = "sm-api-gateway"
DISPLAY_NAME = "SM API Gateway"
DESCRIPTION = "企业 API 网关：鉴权、限流、熔断、灰度与请求审计"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("SM_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()]
REQUESTS = {"total": 0, "errors": 0, "latency_ms_total": 0.0}
INTEGRATION_DEPENDENCIES = ['sm-iam', 'sm-audit-log-center', 'sm-observability']
INTEGRATION_EVENTS = ["health.checked", "resource.changed", "audit.recorded"]

app = FastAPI(title=DISPLAY_NAME, version=VERSION, description=DESCRIPTION, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

class Item(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    owner: str = Field(default="平台工程部", min_length=1, max_length=80)
    priority: Literal["P0", "P1", "P2", "P3"] = "P1"
    status: Literal["planned", "active", "review", "closed"] = "active"

ITEMS: list[dict[str, object]] = [
    {"id": "demo-1", "name": "核心能力基线", "owner": "平台工程部", "priority": "P1", "status": "active", "created_at": datetime.now(UTC).isoformat()},
    {"id": "demo-2", "name": "安全与审计策略", "owner": "安全合规部", "priority": "P1", "status": "review", "created_at": datetime.now(UTC).isoformat()},
]

@app.middleware("http")
async def security_headers(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000
    REQUESTS["total"] += 1
    REQUESTS["latency_ms_total"] += elapsed
    if response.status_code >= 500:
        REQUESTS["errors"] += 1
    response.headers["X-Request-Id"] = request_id[:64]
    response.headers["X-Process-Time-Ms"] = f"{elapsed:.2f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response

@app.get("/", include_in_schema=False)
def console() -> FileResponse:
    return FileResponse("app/static/index.html")

@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "service": SERVICE_NAME, "name": DISPLAY_NAME, "version": VERSION, "timestamp": datetime.now(UTC).isoformat()}

@app.get("/readyz")
def readyz() -> dict[str, object]:
    return {"status": "ready", "service": SERVICE_NAME, "checks": {"runtime": "ok", "configuration": "ok"}}

@app.get("/api/overview")
def overview() -> dict[str, object]:
    return {"platform": {"name": DISPLAY_NAME, "version": VERSION, "description": DESCRIPTION}, "items": ITEMS, "total": len(ITEMS), "active": sum(1 for i in ITEMS if i["status"] == "active")}

@app.post("/api/items", status_code=status.HTTP_201_CREATED)
def create_item(payload: Item) -> dict[str, object]:
    item = {"id": str(uuid.uuid4()), **payload.model_dump(), "created_at": datetime.now(UTC).isoformat()}
    ITEMS.append(item)
    return item

@app.patch("/api/items/{item_id}/status")
def update_item_status(item_id: str, item_status: Literal["planned", "active", "review", "closed"]) -> dict[str, object]:
    for item in ITEMS:
        if item["id"] == item_id:
            item["status"] = item_status
            return item
    raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")

@app.get("/api/ops/metrics")
def metrics() -> dict[str, object]:
    total = int(REQUESTS["total"])
    avg = round(float(REQUESTS["latency_ms_total"]) / total, 2) if total else 0.0
    return {"service": SERVICE_NAME, "version": VERSION, "requests_total": total, "errors_total": int(REQUESTS["errors"]), "avg_latency_ms": avg}


@app.get("/api/integration/manifest")
def integration_manifest() -> dict[str, object]:
    return {
        "service": SERVICE_NAME,
        "name": DISPLAY_NAME,
        "version": VERSION,
        "dependencies": INTEGRATION_DEPENDENCIES,
        "events": INTEGRATION_EVENTS,
        "health_path": "/health",
        "metrics_path": "/api/ops/metrics",
        "overview_path": "/api/overview",
    }
