"""SM Enterprise Suite 共享企业服务基础层。

集中承载企业级横切能力：
- 安全响应头 / CSP / TrustedHost / 请求体限制 / 接口速率限制
- 国密 SM3 摘要与 SM4-CBC（带 SM3 MAC 完整性校验，防密文篡改）
- SM4 密钥仅允许通过环境变量 SM4_KEY_HEX 注入；开发环境使用进程内临时密钥，禁止落库
- JWT(HS256) 校验；生产环境未配置认证凭据时对受保护 API 采取 fail-closed
- SQLite 持久化（WAL）与本地审计落库 + 异步转发集中审计中心
- 运维指标（请求量 / 错误量 / 平均延迟）与 Prometheus 文本指标
- 服务契约 /api/integration/manifest 与安全基线 /api/security/baseline
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from gmssl import func, sm3
from gmssl.sm4 import SM4_DECRYPT, SM4_ENCRYPT, CryptSM4

__all__ = ["create_app", "get_db", "record_audit", "sm3_hex", "sm4_encrypt", "sm4_decrypt", "verify_jwt", "require_internal_token", "require_principal"]

_ENV = os.getenv("SM_ENV", "development").lower()
_PRODUCTION = _ENV == "production"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_logger = logging.getLogger("sm.base")


# --------------------------------------------------------------------------- #
# 全局状态
# --------------------------------------------------------------------------- #
_metrics_lock = threading.Lock()
_metrics = {"requests_total": 0, "errors_total": 0, "latency_ms_total": 0.0}

_rate_buckets: dict[str, tuple[int, int]] = {}
_rate_lock = threading.Lock()

_db_conn: sqlite3.Connection | None = None
_db_lock = threading.RLock()
_db_path: str = ""

_ephemeral_sm4_key: bytes | None = None


# --------------------------------------------------------------------------- #
# 基础配置
# --------------------------------------------------------------------------- #
def allowed_hosts() -> list[str]:
    return [h.strip() for h in os.getenv("SM_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()]


def max_request_bytes() -> int:
    return int(os.getenv("SM_MAX_REQUEST_BYTES", "1048576"))


def rate_window() -> int:
    return int(os.getenv("SM_RATE_WINDOW_SECONDS", "60"))


def rate_max() -> int:
    return int(os.getenv("SM_RATE_MAX_REQUESTS", "600"))


def internal_api_key() -> str:
    return os.getenv("SM_INTERNAL_API_KEY", "")


def jwt_secret() -> str:
    return os.getenv("SM_JWT_SECRET", "")


def audit_center_url() -> str:
    return os.getenv("SM_AUDIT_CENTER_URL", "")


def database_path() -> str:
    return os.getenv("SM_DATABASE_PATH", "")


def is_production() -> bool:
    return _PRODUCTION


# --------------------------------------------------------------------------- #
# 国密 SM3 / SM4（带完整性）
# --------------------------------------------------------------------------- #
def sm3_hex(value: bytes) -> str:
    return sm3.sm3_hash(func.bytes_to_list(value))


def _sm4_key() -> bytes:
    """SM4 主密钥：仅来自环境变量；生产环境缺失时 fail-closed，开发环境使用进程内临时密钥。"""
    global _ephemeral_sm4_key
    configured = os.getenv("SM4_KEY_HEX", "").strip()
    if configured:
        key = bytes.fromhex(configured)
        if len(key) != 16:
            raise RuntimeError("SM4_KEY_HEX 必须是 32 位十六进制（16 字节）密钥")
        return key
    if _PRODUCTION:
        raise RuntimeError("生产环境必须通过 SM4_KEY_HEX 注入 SM4 主密钥，禁止落库或默认值")
    if _ephemeral_sm4_key is None:
        _ephemeral_sm4_key = secrets.token_bytes(16)
    return _ephemeral_sm4_key


def derive_key(label: str) -> bytes:
    """从主密钥派生用途隔离子密钥，避免加密与完整性复用同一密钥。"""
    return bytes.fromhex(sm3_hex(_sm4_key() + label.encode("utf-8")))[:16]


def sm4_encrypt(value: bytes, label: str = "sm4-encryption") -> str:
    """SM4-CBC 加密并附加 SM3 MAC，返回 sm4$iv$ct$mac，防篡改。"""
    enc_key, mac_key, iv = derive_key(label), derive_key("sm3-mac"), secrets.token_bytes(16)
    cipher = CryptSM4()
    cipher.set_key(enc_key, SM4_ENCRYPT)
    ciphertext = cipher.crypt_cbc(iv, value)
    mac = sm3_hex(mac_key + iv + ciphertext)
    return f"sm4${iv.hex()}${ciphertext.hex()}${mac}"


def sm4_decrypt(token: str, label: str = "sm4-encryption") -> bytes:
    if not token.startswith("sm4$"):
        raise ValueError("密文格式无效")
    _, iv_hex, ct_hex, mac = token.split("$", 3)
    enc_key, mac_key, iv, ciphertext = derive_key(label), derive_key("sm3-mac"), bytes.fromhex(iv_hex), bytes.fromhex(ct_hex)
    if not secrets.compare_digest(sm3_hex(mac_key + iv + ciphertext), mac):
        raise ValueError("密文完整性校验失败")
    cipher = CryptSM4()
    cipher.set_key(enc_key, SM4_DECRYPT)
    return cipher.crypt_cbc(iv, ciphertext)


# --------------------------------------------------------------------------- #
# JWT(HS256)
# --------------------------------------------------------------------------- #
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def verify_jwt(token: str) -> dict[str, Any] | None:
    secret = jwt_secret()
    if not secret:
        return None
    try:
        header_b64, claims_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{claims_b64}".encode()
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_b64)):
            return None
        claims = json.loads(_b64url_decode(claims_b64))
        if int(claims.get("exp", 0)) < int(time.time()):
            return None
        return claims
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 速率限制
# --------------------------------------------------------------------------- #
def consume_rate_limit(key: str, period: int | None = None, maximum: int | None = None) -> None:
    period = period or rate_window()
    maximum = maximum or rate_max()
    with _rate_lock:
        current = int(time.time())
        for bucket_key, (started, _) in list(_rate_buckets.items()):
            if current - started >= period:
                _rate_buckets.pop(bucket_key, None)
        started, count = _rate_buckets.get(key, (current, 0))
        if current - started >= period:
            started, count = current, 0
        if count >= maximum:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "请求过于频繁，请稍后重试")
        _rate_buckets[key] = (started, count + 1)


# --------------------------------------------------------------------------- #
# 持久化
# --------------------------------------------------------------------------- #
def get_db() -> sqlite3.Connection:
    """返回带 WAL 的 SQLite 连接（文件或内存），并保证基础表存在。"""
    global _db_conn, _db_path
    if _db_conn is not None:
        return _db_conn
    with _db_lock:
        if _db_conn is not None:
            return _db_conn
        _db_path = database_path() or ":memory:"
        if _db_path != ":memory:":
            Path(_db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(_db_path, check_same_thread=False, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=15000")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT, service TEXT, action TEXT, actor TEXT,
                timestamp TEXT, request_id TEXT, trace_id TEXT, detail TEXT, integrity TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_audit_events_ts ON audit_events(timestamp DESC);
            """
        )
        if _db_path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        conn.commit()
        _db_conn = conn
        return conn


@contextmanager
def db_ctx():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    finally:
        pass  # 连接常驻，不在此关闭


def setting(key: str, default: str = "") -> str:
    row = get_db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else default


def set_setting(key: str, value: str) -> None:
    get_db().execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    get_db().commit()


def reset_state() -> None:
    """测试用：重置全局数据库连接、指标、速率桶与临时密钥，实现用例间隔离。"""
    global _db_conn, _db_path, _ephemeral_sm4_key
    with _db_lock:
        if _db_conn is not None:
            with suppress(Exception):
                _db_conn.close()
            _db_conn = None
        _db_path = ""
    with _metrics_lock:
        _metrics.update({"requests_total": 0, "errors_total": 0, "latency_ms_total": 0.0})
    with _rate_lock:
        _rate_buckets.clear()
    _ephemeral_sm4_key = None


# --------------------------------------------------------------------------- #
# 审计
# --------------------------------------------------------------------------- #
def _forward_audit(event: dict[str, Any]) -> None:
    import urllib.request as _ur
    try:
        center = audit_center_url()
        if not center:
            return
        body = json.dumps(event, ensure_ascii=False).encode("utf-8")
        req = _ur.Request(
            center.rstrip("/") + "/api/audit/events",
            data=body,
            headers={"Content-Type": "application/json", "X-Internal-Token": internal_api_key()},
            method="POST",
        )
        _ur.urlopen(req, timeout=2)
    except Exception:
        _logger.debug("audit forward failed", exc_info=True)


def record_audit(action: str, actor: str, detail: str = "", request_id: str = "", trace_id: str = "", service: str = "sm-service") -> None:
    event_id = str(uuid.uuid4())
    timestamp = datetime.now(UTC).isoformat()
    event = {
        "event_id": event_id, "service": service, "action": action, "actor": actor,
        "timestamp": timestamp, "request_id": request_id[:64], "trace_id": trace_id[:64], "detail": detail[:2000],
    }
    canonical = json.dumps(event, ensure_ascii=False, sort_keys=True)
    integrity = sm3_hex(canonical.encode("utf-8"))
    with db_ctx() as conn:
        conn.execute(
            "INSERT INTO audit_events (event_id, service, action, actor, timestamp, request_id, trace_id, detail, integrity) VALUES (?,?,?,?,?,?,?,?,?)",
            (event_id, service, action, actor, timestamp, request_id[:64], trace_id[:64], canonical, integrity),
        )
    if audit_center_url():
        threading.Thread(target=_forward_audit, args=(event,), daemon=True).start()


# --------------------------------------------------------------------------- #
# 鉴权辅助
# --------------------------------------------------------------------------- #
def internal_write_allowed(request: Request) -> bool:
    key = internal_api_key()
    if not key:
        return False
    return secrets.compare_digest(request.headers.get("X-Internal-Token", ""), key)


def require_internal_token(request: Request) -> None:
    """写操作依赖：必须携带有效内部写入令牌。"""
    if not internal_write_allowed(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "内部写入令牌无效")


def principal(request: Request) -> dict[str, Any] | None:
    """解析调用者：优先内部令牌（system），其次 Bearer JWT。"""
    if internal_write_allowed(request):
        return {"sub": "system", "role": "internal", "source": "internal-token"}
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        claims = verify_jwt(authorization[7:])
        if claims:
            return {**claims, "source": "jwt"}
    return None


def require_principal(request: Request) -> dict[str, Any]:
    p = principal(request)
    if p is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "认证无效")
    return p


def _is_public_path(path: str, public_paths: set[str]) -> bool:
    if not path.startswith("/api/"):
        return True
    if path in public_paths:
        return True
    # /api/crypto/* 与 /api/security/baseline 等前缀公开
    return any(path.startswith(prefix) for prefix in ("/api/crypto/", "/api/security/", "/api/integration/", "/api/ops/"))


# --------------------------------------------------------------------------- #
# 应用工厂
# --------------------------------------------------------------------------- #
def create_app(
    *,
    service: str,
    name: str,
    description: str,
    version: str,
    port: int,
    dependencies: list[str] | None = None,
    events: list[str] | None = None,
    overview_fn: Callable[[Request], dict[str, Any]] | None = None,
    health_checks: Callable[[], dict[str, Any]] | None = None,
    extra_controls: dict[str, Any] | None = None,
    public_extra_paths: set[str] | None = None,
) -> FastAPI:
    service = service.lower()
    _logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        if _PRODUCTION:
            _sm4_key()  # 生产环境启动即校验密钥注入
        get_db()
        yield

    app = FastAPI(title=name, version=version, description=description, docs_url=None, redoc_url=None, lifespan=_lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())
    app.state.sm_service = service
    app.state.sm_port = port
    _public = set(public_extra_paths or {"/api/overview", "/api/healthz"})
    _overview_fn = overview_fn
    _health_checks = health_checks

    @app.middleware("http")
    async def _enterprise_middleware(request: Request, call_next):
        started = time.perf_counter()
        supplied = request.headers.get("X-Request-Id", "")
        request_id = supplied if _REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        trace_id = request.headers.get("X-Trace-Id", "") or request_id
        request.state.request_id = request_id[:64]
        request.state.trace_id = trace_id[:64]

        response: Response
        path = request.url.path
        if path.startswith("/api/") and not _is_public_path(path, _public) and principal(request) is None:
            # fail-closed：生产环境未配置任何凭据时，受保护 API 一律拒绝
            if _PRODUCTION or internal_api_key() or jwt_secret():
                response = Response(status_code=status.HTTP_401_UNAUTHORIZED, content="认证无效")
            else:
                response = await call_next(request)
        else:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    body_size = int(content_length)
                except ValueError:
                    response = Response(status_code=status.HTTP_400_BAD_REQUEST, content="Invalid Content-Length")
                else:
                    if body_size < 0 or body_size > max_request_bytes():
                        response = Response(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, content="Request body too large")
                    else:
                        try:
                            consume_rate_limit(f"{request.client.host if request.client else 'unknown'}:{path}")
                        except HTTPException as exc:
                            response = Response(status_code=exc.status_code, content=str(exc.detail), headers={"Retry-After": str(rate_window())})
                        else:
                            response = await call_next(request)
            else:
                try:
                    consume_rate_limit(f"{request.client.host if request.client else 'unknown'}:{path}")
                except HTTPException as exc:
                    response = Response(status_code=exc.status_code, content=str(exc.detail), headers={"Retry-After": str(rate_window())})
                else:
                    response = await call_next(request)

        elapsed_ms = (time.perf_counter() - started) * 1000
        with _metrics_lock:
            _metrics["requests_total"] += 1
            _metrics["latency_ms_total"] += elapsed_ms
            if response.status_code >= 500:
                _metrics["errors_total"] += 1
        response.headers["X-Request-Id"] = request_id[:64]
        response.headers["X-Trace-Id"] = trace_id[:64]
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        if _PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cache-Control"] = "no-store" if path.startswith("/api/") else "no-cache"
        return response

    # ------------------------------------------------------------------ #
    # 标准端点
    # ------------------------------------------------------------------ #
    @app.get("/", include_in_schema=False)
    def _console() -> FileResponse:
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/health")
    def _health() -> dict[str, Any]:
        try:
            get_db().execute("SELECT 1").fetchone()
            database = "ok"
        except sqlite3.Error:
            database = "error"
        return {"status": "ok", "service": service, "name": name, "version": version, "database": database, "timestamp": datetime.now(UTC).isoformat()}

    @app.get("/readyz")
    def _ready() -> dict[str, Any]:
        checks: dict[str, Any] = {"runtime": "ok", "configuration": "ok", "database": "ok"}
        if _health_checks is not None:
            checks.update(_health_checks())
        if _PRODUCTION:
            try:
                _sm4_key()
                checks["crypto"] = "configured"
            except RuntimeError:
                checks["crypto"] = "missing-key"
        return {"status": "ready" if all(str(v).lower() in {"ok", "ready", "configured", "true", "1"} for v in checks.values()) else "degraded", "service": service, "checks": checks}

    @app.get("/api/overview")
    def _overview(request: Request) -> dict[str, Any]:
        payload: dict[str, Any] = {"platform": {"name": name, "version": version, "description": description}, "service": service, "healthy": True}
        if _overview_fn is not None:
            payload.update(_overview_fn(request))
        return payload

    @app.get("/api/ops/metrics")
    def _ops_metrics() -> dict[str, Any]:
        with _metrics_lock:
            snapshot = dict(_metrics)
        total = int(snapshot["requests_total"])
        avg = round(float(snapshot["latency_ms_total"]) / total, 2) if total else 0.0
        return {"service": service, "version": version, "requests_total": total, "errors_total": int(snapshot["errors_total"]), "avg_latency_ms": avg}

    @app.get("/metrics")
    def _prometheus_metrics() -> Response:
        with _metrics_lock:
            snapshot = dict(_metrics)
        body = (
            f"sm_{service}_requests_total {int(snapshot['requests_total'])}\n"
            f"sm_{service}_errors_total {int(snapshot['errors_total'])}\n"
            f"sm_{service}_latency_ms_total {snapshot['latency_ms_total']:.2f}\n"
        )
        return Response(content=body, media_type="text/plain; version=0.0.4")

    @app.get("/api/integration/manifest")
    def _manifest() -> dict[str, Any]:
        return {
            "service": service,
            "name": name,
            "version": version,
            "dependencies": dependencies or [],
            "events": events or ["health.checked", "resource.changed", "audit.recorded"],
            "health_path": "/health",
            "metrics_path": "/api/ops/metrics",
            "overview_path": "/api/overview",
        }

    @app.get("/api/security/baseline")
    def _security_baseline() -> dict[str, Any]:
        controls: dict[str, Any] = {
            "trusted_host": True,
            "security_headers": True,
            "csp": True,
            "rate_limit": True,
            "request_size_limit": True,
            "sm3": True,
            "sm4": True,
            "sm4_integrity_mac": True,
            "internal_token": bool(internal_api_key()),
            "jwt": bool(jwt_secret()),
            "audit_persistence": True,
            "audit_forwarding": bool(audit_center_url()),
            "fail_closed": _PRODUCTION,
        }
        if extra_controls:
            controls.update(extra_controls)
        return {"service": service, "version": version, "controls": controls, "recommended": ["OIDC/MFA", "KMS/HSM", "centralized audit", "OpenTelemetry"]}

    @app.post("/api/crypto/sm3")
    def _crypto_sm3(payload: dict[str, str]) -> dict[str, str]:
        value = payload.get("value", "")
        if len(value) > 10000:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "内容过大")
        return {"algorithm": "SM3", "digest": sm3_hex(value.encode("utf-8"))}

    @app.post("/api/crypto/encrypt")
    def _crypto_encrypt(payload: dict[str, str]) -> dict[str, str]:
        value = payload.get("value", "")
        if len(value) > 10000:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "内容过大")
        return {"algorithm": "SM4-CBC+SM3", "ciphertext": sm4_encrypt(value.encode("utf-8"))}

    @app.post("/api/crypto/decrypt")
    def _crypto_decrypt(payload: dict[str, str]) -> dict[str, str]:
        try:
            plaintext = sm4_decrypt(payload.get("value", ""))
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        return {"algorithm": "SM4-CBC+SM3", "plaintext": plaintext.decode("utf-8")}

    @app.get("/api/crypto/status")
    def _crypto_status() -> dict[str, Any]:
        return {
            "algorithm": "SM3/SM4-CBC",
            "sm3": "enabled",
            "sm4": "enabled",
            "integrity": "SM3-MAC",
            "key_source": "SM4_KEY_HEX environment" if os.getenv("SM4_KEY_HEX") else ("ephemeral (dev)" if not _PRODUCTION else "missing"),
            "fail_closed": _PRODUCTION,
        }

    return app
