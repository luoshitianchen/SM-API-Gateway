"""代理转发服务：根据数据库路由规则将请求转发到上游服务。

核心职责：
1. 加载数据库中 active 状态的路由规则，按 priority 升序匹配；
2. 使用 httpx.AsyncClient 将原始请求（含业务头与 query string）转发到上游；
3. 记录转发日志（路径、上游、状态码、耗时）。
"""
from __future__ import annotations

import time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.logging import get_logger
from app.models.gateway_route import GatewayRoute

logger = get_logger("proxy")

# ── 逐跳（hop-by-hop）头：转发时必须剥离，否则会导致连接复用问题 ──
_HOP_BY_HOP_REQUEST = {
    "host", "content-length", "connection", "keep-alive",
    "proxy-authenticate", "proxy-authorization", "te", "trailer",
    "transfer-encoding", "upgrade", "x-forwarded-for", "x-forwarded-proto",
}
_HOP_BY_HOP_RESPONSE = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "content-encoding",
}

# 模块级共享异步客户端：长连接复用，避免每次请求重建连接池
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """获取共享的 httpx 异步客户端（懒加载）。"""
    global _client
    if _client is None:
        # 限制连接池，防止转发风暴耗尽资源
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0), limits=limits)
    return _client


async def close_client() -> None:
    """关闭共享客户端，释放连接池（应用关闭时调用）。"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _pattern_prefix(pattern: str) -> str:
    """将路径模式转换为前缀。

    支持两种写法：
    - 前缀通配：``/api/iam/*`` → 前缀 ``/api/iam/``
    - 精确匹配：``/api/iam/users`` → 自身
    """
    if pattern.endswith("/*"):
        return pattern[:-1]  # 去掉末尾 ``*``，保留结尾斜杠
    if pattern.endswith("*"):
        return pattern[:-1]
    return pattern


def match_route(path: str, routes: list[GatewayRoute]) -> GatewayRoute | None:
    """在路由列表中匹配第一个命中的规则（列表已按 priority 升序）。

    匹配规则：
    - 精确模式要求 path 与 pattern 完全相等；
    - 通配模式（``/*`` 结尾）要求 path 以前缀开头；
    - 同优先级下数据库已按 created_at 倒序，先注册的优先。
    """
    for route in routes:
        pattern = route.path_pattern
        if pattern.endswith("*"):
            prefix = _pattern_prefix(pattern)
            if path.startswith(prefix):
                return route
        elif path == pattern:
            return route
    return None


async def load_active_routes(session: AsyncSession) -> list[GatewayRoute]:
    """加载所有 active 路由，按 priority 升序、创建时间倒序返回。"""
    stmt = (
        select(GatewayRoute)
        .where(GatewayRoute.status == "active")
        .order_by(GatewayRoute.priority.asc(), GatewayRoute.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _is_method_allowed(route: GatewayRoute, method: str) -> bool:
    """检查路由规则是否允许当前 HTTP 方法。"""
    allowed = {m.strip().upper() for m in (route.methods or "").split(",") if m.strip()}
    return method.upper() in allowed


def _filter_request_headers(headers: dict[str, str]) -> dict[str, str]:
    """剥离逐跳头与网关自身注入头，保留业务头（含 X-Internal-Token）。"""
    return {
        k: v for k, v in headers.items()
        if k.lower() not in _HOP_BY_HOP_REQUEST
    }


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    """剥离上游响应中的逐跳头，避免客户端与网关连接语义混乱。"""
    return {
        k: v for k, v in headers.items()
        if k.lower() not in _HOP_BY_HOP_RESPONSE
    }


async def forward(
    method: str,
    path: str,
    query_string: bytes,
    headers: dict[str, str],
    body: bytes,
) -> tuple[int, bytes, dict[str, str], str]:
    """执行一次转发，返回 (状态码, 响应体, 响应头, 上游地址)。

    参数：
        method: 原始 HTTP 方法（GET/POST/...）
        path: 去掉 ``/proxy`` 前缀后的请求路径，如 ``/api/iam/users``
        query_string: 原始 query string 字节串
        headers: 原始请求头字典
        body: 原始请求体字节串
    """
    # 1. 独立数据库会话：转发请求不占用业务请求的 session
    async with async_session() as session:
        routes = await load_active_routes(session)

    route = match_route(path, routes)
    if route is None:
        logger.info("proxy.no_route path=%s", path)
        return 404, b'{"detail":"no route matched"}', {"content-type": "application/json"}, ""

    if not _is_method_allowed(route, method):
        logger.info("proxy.method_not_allowed path=%s method=%s", path, method)
        return 405, b'{"detail":"method not allowed by route"}', {"content-type": "application/json"}, route.upstream_url

    # 2. 拼接上游目标 URL
    base = route.upstream_url.rstrip("/")
    target_url = f"{base}{path}"
    if query_string:
        target_url = f"{target_url}?{query_string.decode('ascii', errors='ignore')}"

    # 3. 过滤请求头并转发
    fwd_headers = _filter_request_headers(headers)
    started = time.perf_counter()
    client = get_client()
    try:
        resp = await client.request(
            method=method,
            url=target_url,
            headers=fwd_headers,
            content=body,
            follow_redirects=False,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.warning(
            "proxy.upstream_error path=%s upstream=%s error=%s elapsed_ms=%.2f",
            path, route.upstream_url, type(exc).__name__, elapsed_ms,
        )
        return 502, b'{"detail":"bad gateway: upstream unreachable"}', {
            "content-type": "application/json"}, route.upstream_url

    elapsed_ms = (time.perf_counter() - started) * 1000
    resp_headers = _filter_response_headers(resp.headers)

    # 4. 记录转发日志
    logger.info(
        "proxy.forward path=%s upstream=%s status=%d elapsed_ms=%.2f route_id=%s",
        path, route.upstream_url, resp.status_code, elapsed_ms, route.id,
    )

    return resp.status_code, resp.content, resp_headers, route.upstream_url
