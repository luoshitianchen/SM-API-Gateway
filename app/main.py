"""SM API Gateway —— 企业 API 网关：路由、上游代理、限流、访问日志与安全校验。"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field

from app import base

SERVICE = "sm-api-gateway"
VERSION = "2.0.1"
NAME = "SM API Gateway"
DESCRIPTION = "企业 API 网关：路由、上游代理、限流、访问日志与安全校验"
PORT = 8310


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _init() -> None:
    with base.db_ctx() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS routes (
                id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, method TEXT NOT NULL DEFAULT 'GET',
                upstream TEXT NOT NULL, rate_limit_per_min INTEGER NOT NULL DEFAULT 100,
                auth_required INTEGER NOT NULL DEFAULT 1, enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS requests_log (
                id TEXT PRIMARY KEY, route_id TEXT, route_path TEXT, method TEXT,
                status_code INTEGER, latency_ms REAL, remote_ip TEXT, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_requests_time ON requests_log(created_at DESC);
            """
        )


app = base.create_app(
    service=SERVICE, name=NAME, description=DESCRIPTION, version=VERSION, port=PORT,
    dependencies=["sm-iam", "sm-api-developer-portal", "sm-audit-log-center"],
    events=["route.created", "proxy.forwarded", "rate.limited", "route.disabled"],
    overview_fn=lambda _r: {
        "summary": {
            "routes": base.get_db().execute("SELECT COUNT(*) FROM routes").fetchone()[0],
            "requests": base.get_db().execute("SELECT COUNT(*) FROM requests_log").fetchone()[0],
        }
    },
)
_init()


class RouteIn(BaseModel):
    path: str = Field(min_length=2, max_length=200)
    method: str = Field(default="GET", pattern=r"^(GET|POST|PUT|PATCH|DELETE|ANY)$")
    upstream: str = Field(min_length=5, max_length=300)
    rate_limit_per_min: int = Field(default=100, ge=1, le=100000)
    auth_required: int = Field(default=1, ge=0, le=1)


class ProxyIn(BaseModel):
    path: str = Field(min_length=2, max_length=200)
    method: str = Field(default="GET", pattern=r"^(GET|POST|PUT|PATCH|DELETE)$")
    body: dict[str, Any] = Field(default_factory=dict)


class EnableIn(BaseModel):
    enabled: int = Field(ge=0, le=1)


def _match_route(conn, method: str, path: str):
    """按最长前缀匹配已注册路由；只允许白名单路由转发，杜绝任意路径代理。"""
    candidates = conn.execute("SELECT * FROM routes WHERE enabled=1 AND (method=? OR method='ANY')", (method,)).fetchall()
    best, best_len = None, -1
    for route in candidates:
        prefix = route["path"]
        if (prefix == path or path.startswith(prefix.rstrip("/") + "/") or prefix == "ANY") and len(prefix) > best_len:
            best, best_len = route, len(prefix)
    return best


@app.get("/api/gateway/routes")
def list_routes() -> dict[str, Any]:
    with base.db_ctx() as conn:
        rows = conn.execute("SELECT * FROM routes ORDER BY created_at DESC").fetchall()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@app.post("/api/gateway/routes", status_code=status.HTTP_201_CREATED)
def create_route(payload: RouteIn, request: Request) -> dict[str, Any]:
    base.require_internal_token(request)
    route_id = str(uuid.uuid4())
    with base.db_ctx() as conn:
        try:
            conn.execute("INSERT INTO routes VALUES (?,?,?,?,?,?,?,?)", (route_id, payload.path, payload.method, payload.upstream, payload.rate_limit_per_min, payload.auth_required, 1, _now()))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status.HTTP_409_CONFLICT, "路由已存在") from exc
    return {"id": route_id, "path": payload.path}


@app.post("/api/gateway/routes/{route_id}/status")
def set_route_status(route_id: str, payload: EnableIn, request: Request) -> dict[str, Any]:
    base.require_internal_token(request)
    with base.db_ctx() as conn:
        if conn.execute("UPDATE routes SET enabled=? WHERE id=?", (payload.enabled, route_id)).rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "路由不存在")
        base.record_audit("route.disabled", "internal", f"route={route_id} enabled={payload.enabled}", getattr(request.state, "request_id", ""), getattr(request.state, "trace_id", ""), SERVICE)
    return {"id": route_id, "enabled": payload.enabled}


@app.delete("/api/gateway/routes/{route_id}")
def delete_route(route_id: str, request: Request) -> dict[str, Any]:
    base.require_internal_token(request)
    with base.db_ctx() as conn:
        if conn.execute("DELETE FROM routes WHERE id=?", (route_id,)).rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "路由不存在")
    return {"deleted": True}


@app.post("/api/gateway/proxy")
def proxy(payload: ProxyIn, request: Request) -> dict[str, Any]:
    """统一入口：命中白名单路由 → 校验鉴权 → 限流 → 转发(模拟) → 记录访问日志。"""
    started = time.perf_counter()
    with base.db_ctx() as conn:
        route = _match_route(conn, payload.method, payload.path)
        if not route:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "未匹配到可用路由")
        # 鉴权：需鉴权路由必须携带有效网关 API Key
        if route["auth_required"]:
            api_key = request.headers.get("X-Api-Key", "")
            if not api_key or not _validate_api_key(api_key):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API Key 无效或缺失")
        # 限流：最近 60 秒内该路由请求数
        window_start = datetime.now(UTC).timestamp() - 60
        recent = conn.execute("SELECT COUNT(*) FROM requests_log WHERE route_id=? AND created_at>=?", (route["id"], _iso_from_ts(window_start))).fetchone()[0]
        if recent >= route["rate_limit_per_min"]:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "超出限流配额")
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        log_id = str(uuid.uuid4())
        conn.execute("INSERT INTO requests_log (id, route_id, route_path, method, status_code, latency_ms, remote_ip, created_at) VALUES (?,?,?,?,?,?,?,?)", (log_id, route["id"], route["path"], payload.method, 200, latency_ms, request.client.host if request.client else "unknown", _now()))
        base.record_audit("proxy.forwarded", "internal", f"route={route['path']} method={payload.method}", getattr(request.state, "request_id", ""), getattr(request.state, "trace_id", ""), SERVICE)
    return {
        "status": 200,
        "route_id": route["id"],
        "upstream": route["upstream"],
        "method": payload.method,
        "latency_ms": latency_ms,
        "message": f"已转发至上游 {route['upstream']}",
    }


def _iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _call_portal_validate(api_key: str) -> bool:
    """真实回调开发者门户校验 API Key（哈希匹配）；未配置门户或调用失败一律拒绝。"""
    portal = os.getenv("SM_API_PORTAL_URL", "")
    if not portal or not api_key:
        return False
    try:
        import json as _json
        import urllib.request as _ur

        body = _json.dumps({"api_key": api_key}).encode("utf-8")
        req = _ur.Request(
            portal.rstrip("/") + "/api/portal/keys/validate",
            data=body,
            headers={"Content-Type": "application/json", "X-Internal-Token": base.internal_api_key()},
            method="POST",
        )
        with _ur.urlopen(req, timeout=2) as resp:  # noqa: S310 (受控内部调用)
            return resp.status == 200
    except Exception:
        return False


def _validate_api_key(api_key: str) -> bool:
    """API Key 校验：仅接受开发者门户的哈希匹配结果；未配置门户时 fail-closed，不做前缀/长度弱校验。"""
    return _call_portal_validate(api_key)


@app.get("/api/gateway/requests")
def list_requests(limit: int = 100) -> dict[str, Any]:
    limit = max(1, min(500, limit))
    with base.db_ctx() as conn:
        rows = conn.execute("SELECT * FROM requests_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@app.get("/api/gateway/stats")
def stats() -> dict[str, Any]:
    with base.db_ctx() as conn:
        def _count(sql: str) -> int:
            return conn.execute(sql).fetchone()[0]
        return {
            "routes": _count("SELECT COUNT(*) FROM routes"),
            "enabled_routes": _count("SELECT COUNT(*) FROM routes WHERE enabled=1"),
            "requests": _count("SELECT COUNT(*) FROM requests_log"),
            "last_5_min": _count(f"SELECT COUNT(*) FROM requests_log WHERE created_at>='{_iso_from_ts(datetime.now(UTC).timestamp() - 300)}'"),
        }
