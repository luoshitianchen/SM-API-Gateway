"""代理转发路由：catch-all 入口，根据数据库路由规则转发到上游服务。

外部调用形式::

    GET /proxy/api/iam/users  →  匹配 /api/iam/* 规则  →  转发到上游
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.core.security import internal_write_allowed
from app.services import proxy as proxy_service

proxy_router = APIRouter(prefix="/proxy", tags=["gateway-proxy"])


@proxy_router.api_route("/{path:path}", methods=[
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS",
])
async def proxy_handler(path: str, request: Request) -> Response:
    """统一代理入口：校验内部令牌后按路由规则转发。"""
    # 内部令牌校验：/proxy 不在 SecurityMiddleware 的 /api/ 拦截范围内，
    # 因此在这里显式校验 X-Internal-Token，防止裸奔。
    if not internal_write_allowed(request):
        return Response(status_code=403, content="内部令牌无效")

    # 规范化路径：确保以斜杠开头
    full_path = f"/{path}" if not path.startswith("/") else path

    # 读取原始请求体（字节级透传，不做反序列化）
    body = await request.body()

    # 调用转发服务
    status_code, resp_body, resp_headers, _upstream = await proxy_service.forward(
        method=request.method,
        path=full_path,
        query_string=request.url.query.encode("ascii", errors="ignore"),
        headers=dict(request.headers),
        body=body,
    )

    return Response(
        content=resp_body,
        status_code=status_code,
        headers=resp_headers,
        media_type=resp_headers.get("content-type"),
    )
