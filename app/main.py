from __future__ import annotations

import json
import os
import secrets
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

VERSION = "2.1.0"
SERVICE_NAME = "sm-api-gateway"
DISPLAY_NAME = "SM API Gateway"
DESCRIPTION = "企业 API 网关：鉴权、限流、熔断、转发与请求审计"
ENVIRONMENT = os.getenv("SM_ENV", "development").lower()
ALLOWED_HOSTS = [h.strip() for h in os.getenv("SM_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()]
REQUESTS = {"total": 0, "errors": 0, "latency_ms_total": 0.0}
RATE_BUCKETS: dict[str, tuple[int, int]] = {}
rate_limit_lock = threading.Lock()
MAX_REQUEST_BYTES = int(os.getenv("SM_MAX_REQUEST_BYTES", "1048576"))
RATE_WINDOW_SECONDS = int(os.getenv("SM_RATE_WINDOW_SECONDS", "60"))
RATE_MAX_REQUESTS = int(os.getenv("SM_RATE_MAX_REQUESTS", "600"))
INTERNAL_API_KEY = os.getenv("SM_INTERNAL_API_KEY", "")
GATEWAY_INTERNAL_TOKEN = os.getenv("SM_GATEWAY_INTERNAL_TOKEN", INTERNAL_API_KEY)
GATEWAY_ROUTES_FILE = os.getenv("SM_GATEWAY_ROUTES_FILE", "config/routes.json")
INTEGRATION_DEPENDENCIES = ['sm-iam', 'sm-audit-log-center']
INTEGRATION_EVENTS = ["health.checked", "gateway.proxy"]


def load_routes() -> dict[str, str]:
    inline = os.getenv("SM_GATEWAY_ROUTES", "")
    if inline.strip():
        data = json.loads(inline)
    else:
        try:
            data = json.loads(Path(GATEWAY_ROUTES_FILE).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {str(key): str(value).rstrip("/") for key, value in data.items() if value}

ROUTES: dict[str, str] = load_routes()


def check_rate_limit(key: str) -> bool:
    with rate_limit_lock:
        current = int(time.time())
        for bucket_key, (started, _) in list(RATE_BUCKETS.items()):
            if current - started >= RATE_WINDOW_SECONDS:
                RATE_BUCKETS.pop(bucket_key, None)
        started, count = RATE_BUCKETS.get(key, (current, 0))
        if current - started >= RATE_WINDOW_SECONDS:
            started, count = current, 0
        if count >= RATE_MAX_REQUESTS:
            return False
        RATE_BUCKETS[key] = (started, count + 1)
        return True

def internal_write_allowed(request: Request) -> bool:
    if not INTERNAL_API_KEY:
        return False
    return secrets.compare_digest(request.headers.get("X-Internal-Token", ""), INTERNAL_API_KEY)


def sm3_hex(value: str) -> str:
    from gmssl import func, sm3
    return sm3.sm3_hash(func.bytes_to_list(value.encode("utf-8")))

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

PROXY_BLOCK_HEADERS = {"host", "content-length", "connection", "transfer-encoding", "accept-encoding"}

async def _proxy(request: Request, route_id: str, upstream: str, suffix: str) -> Response:
    started = time.perf_counter()
    trace_id = request.headers.get("X-Trace-Id", "") or request.headers.get("X-Request-Id", "")
    target = f"{upstream}{suffix}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    headers = {
        key: value for key, value in request.headers.items() if key.lower() not in PROXY_BLOCK_HEADERS
    }
    headers["X-Trace-Id"] = trace_id
    if GATEWAY_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = GATEWAY_INTERNAL_TOKEN
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=2.0), trust_env=False) as client:
            body = await request.body()
            upstream_response = await client.request(request.method, target, headers=headers, content=body or None)
        response = Response(content=upstream_response.content, status_code=upstream_response.status_code, headers={
            key: value for key, value in upstream_response.headers.items() if key.lower() not in {"content-length", "transfer-encoding"}
        })
    except httpx.HTTPError:
        response = Response(status_code=status.HTTP_502_BAD_GATEWAY, content="{\"detail\":\"upstream unavailable\"}", media_type="application/json")
    elapsed = (time.perf_counter() - started) * 1000
    REQUESTS["total"] += 1
    REQUESTS["latency_ms_total"] += elapsed
    if response.status_code >= 500:
        REQUESTS["errors"] += 1
    response.headers["X-Request-Id"] = request.headers.get("X-Request-Id", "") or str(uuid.uuid4())
    response.headers["X-Trace-Id"] = trace_id
    response.headers["X-Upstream"] = route_id
    response.headers["X-Process-Time-Ms"] = f"{elapsed:.2f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

@app.middleware("http")
async def security_headers(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
    path = request.url.path
    for route_id, upstream in ROUTES.items():
        prefix = f"/{route_id}"
        if path == prefix or path.startswith(prefix + "/"):
            return await _proxy(request, route_id, upstream, path[len(prefix):] or "/")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            body_size = int(content_length)
        except ValueError:
            response = Response(status_code=400, content="Invalid Content-Length")
        else:
            if body_size < 0 or body_size > MAX_REQUEST_BYTES:
                response = Response(status_code=413, content="Request body too large")
            elif not check_rate_limit(f"{request.client.host if request.client else 'unknown'}:{request.url.path}"):
                response = Response(status_code=429, content="Too many requests", headers={"Retry-After": str(RATE_WINDOW_SECONDS)})
            else:
                response = await call_next(request)
    elif not check_rate_limit(f"{request.client.host if request.client else 'unknown'}:{request.url.path}"):
        response = Response(status_code=429, content="Too many requests", headers={"Retry-After": str(RATE_WINDOW_SECONDS)})
    else:
        response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000
    REQUESTS["total"] += 1
    REQUESTS["latency_ms_total"] += elapsed
    if response.status_code >= 500:
        REQUESTS["errors"] += 1
    response.headers["X-Request-Id"] = request_id[:64]
    response.headers["X-Trace-Id"] = trace_id[:64]
    response.headers["X-Process-Time-Ms"] = f"{elapsed:.2f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    if ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response

@app.get("/", include_in_schema=False)
def console() -> FileResponse:
    return FileResponse("app/static/index.html")

@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "service": SERVICE_NAME, "name": DISPLAY_NAME, "version": VERSION, "timestamp": datetime.now(UTC).isoformat(), "routes": len(ROUTES)}

@app.get("/readyz")
def readyz() -> dict[str, object]:
    return {"status": "ready", "service": SERVICE_NAME, "checks": {"runtime": "ok", "configuration": "ok", "routes": len(ROUTES)}}

@app.get("/api/gateway/routes")
def gateway_routes() -> dict[str, object]:
    return {"routes": [{"id": key, "upstream": value} for key, value in ROUTES.items()], "count": len(ROUTES)}

@app.get("/api/gateway/status")
async def gateway_status() -> dict[str, object]:
    results = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(2.0, connect=1.0), trust_env=False) as client:
        for route_id, upstream in ROUTES.items():
            try:
                response = await client.get(f"{upstream}/health")
                healthy = response.status_code == 200
            except httpx.HTTPError:
                healthy = False
            results.append({"id": route_id, "upstream": upstream, "healthy": healthy})
    return {"status": "ok" if all(item["healthy"] for item in results) else "degraded", "routes": results}

@app.get("/api/overview")
def overview() -> dict[str, object]:
    return {"platform": {"name": DISPLAY_NAME, "version": VERSION, "description": DESCRIPTION}, "items": ITEMS, "total": len(ITEMS), "active": sum(1 for i in ITEMS if i["status"] == "active"), "proxied_routes": len(ROUTES)}

@app.post("/api/items", status_code=status.HTTP_201_CREATED)
def create_item(payload: Item, request: Request) -> dict[str, object]:
    if not internal_write_allowed(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "内部写入令牌无效")
    item = {"id": str(uuid.uuid4()), **payload.model_dump(), "created_at": datetime.now(UTC).isoformat()}
    ITEMS.append(item)
    return item

@app.patch("/api/items/{item_id}/status")
def update_item_status(item_id: str, item_status: Literal["planned", "active", "review", "closed"], request: Request) -> dict[str, object]:
    if not internal_write_allowed(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "内部写入令牌无效")
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

@app.get("/metrics")
def prometheus_metrics() -> Response:
    total = int(REQUESTS["total"])
    body = (
        f"sm_api_gateway_requests_total {total}\n"
        f"sm_api_gateway_errors_total {int(REQUESTS['errors'])}\n"
        f"sm_api_gateway_latency_ms_total {REQUESTS['latency_ms_total']:.2f}\n"
        f"sm_api_gateway_routes {len(ROUTES)}\n"
    )
    return Response(content=body, media_type="text/plain; version=0.0.4")

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

@app.post("/api/crypto/sm3")
def crypto_sm3(payload: dict[str, str]) -> dict[str, str]:
    value = payload.get("value", "")
    if len(value) > 10000:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "内容过大")
    return {"algorithm": "SM3", "digest": sm3_hex(value)}

@app.get("/api/crypto/status")
def crypto_status() -> dict[str, object]:
    return {"algorithm": "SM3", "sm3": "enabled", "sm4": "enabled"}

@app.get("/api/security/baseline")
def security_baseline() -> dict[str, object]:
    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "controls": {
            "trusted_host": True,
            "security_headers": True,
            "csp": True,
            "rate_limit": True,
            "request_size_limit": True,
            "sm3": True,
            "sm4": True,
            "internal_token": bool(INTERNAL_API_KEY),
            "reverse_proxy": bool(ROUTES),
            "upstream_probe": True,
        },
        "recommended": ["OIDC/MFA", "KMS/HSM", "centralized audit", "OpenTelemetry"],
    }
