"""网关业务域路由：路由规则 / 限流规则 / 密钥 / 上游健康。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.gateway import (
    ApiKeyCreate,
    ApiKeyStatusUpdate,
    ApiKeyUpdate,
    RateLimitRuleCreate,
    RateLimitRuleStatusUpdate,
    RateLimitRuleUpdate,
    RouteCreate,
    RouteStatusUpdate,
    RouteUpdate,
    UpstreamHealthCreate,
    UpstreamHealthStatusUpdate,
    UpstreamHealthUpdate,
)
from app.services.gateway import (
    ApiKeyService,
    RateLimitRuleService,
    RouteService,
    UpstreamHealthService,
)

# ── 路由规则 ──
routes_router = APIRouter(prefix="/api/gateway/routes", tags=["gateway-routes"])


@routes_router.get("")
async def list_routes(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    keyword: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RouteService.list_routes(session, limit, offset, status_filter, keyword)


@routes_router.post("", status_code=status.HTTP_201_CREATED)
async def create_route(
    payload: RouteCreate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RouteService.create_route(session, payload, request)


@routes_router.get("/{route_id}")
async def get_route(
    route_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RouteService.get_route(session, route_id)


@routes_router.patch("/{route_id}")
async def update_route(
    route_id: str, payload: RouteUpdate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RouteService.update_route(session, route_id, payload, request)


@routes_router.patch("/{route_id}/status")
async def update_route_status(
    route_id: str, payload: RouteStatusUpdate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RouteService.update_status(session, route_id, payload, request)


@routes_router.delete("/{route_id}")
async def delete_route(
    route_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RouteService.delete_route(session, route_id, request)


# ── 限流规则 ──
ratelimit_router = APIRouter(prefix="/api/gateway/rate-rules", tags=["gateway-ratelimit"])


@ratelimit_router.get("")
async def list_rules(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    key_type: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RateLimitRuleService.list_rules(session, limit, offset,
                                                  status_filter, key_type, keyword)


@ratelimit_router.post("", status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RateLimitRuleCreate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RateLimitRuleService.create_rule(session, payload, request)


@ratelimit_router.get("/{rule_id}")
async def get_rule(
    rule_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RateLimitRuleService.get_rule(session, rule_id)


@ratelimit_router.patch("/{rule_id}")
async def update_rule(
    rule_id: str, payload: RateLimitRuleUpdate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RateLimitRuleService.update_rule(session, rule_id, payload, request)


@ratelimit_router.patch("/{rule_id}/status")
async def update_rule_status(
    rule_id: str, payload: RateLimitRuleStatusUpdate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RateLimitRuleService.update_status(session, rule_id, payload, request)


@ratelimit_router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await RateLimitRuleService.delete_rule(session, rule_id, request)


# ── 网关密钥 ──
apikey_router = APIRouter(prefix="/api/gateway/api-keys", tags=["gateway-apikeys"])


@apikey_router.get("")
async def list_keys(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    keyword: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await ApiKeyService.list_keys(session, limit, offset, status_filter, keyword)


@apikey_router.post("", status_code=status.HTTP_201_CREATED)
async def create_key(
    payload: ApiKeyCreate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await ApiKeyService.create_key(session, payload, request)


@apikey_router.get("/{key_id}")
async def get_key(
    key_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await ApiKeyService.get_key(session, key_id)


@apikey_router.patch("/{key_id}")
async def update_key(
    key_id: str, payload: ApiKeyUpdate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await ApiKeyService.update_key(session, key_id, payload, request)


@apikey_router.patch("/{key_id}/status")
async def update_key_status(
    key_id: str, payload: ApiKeyStatusUpdate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await ApiKeyService.update_status(session, key_id, payload, request)


@apikey_router.delete("/{key_id}")
async def delete_key(
    key_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await ApiKeyService.delete_key(session, key_id, request)


# ── 上游健康 ──
upstream_router = APIRouter(prefix="/api/gateway/upstreams", tags=["gateway-upstreams"])


@upstream_router.get("")
async def list_upstreams(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    keyword: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await UpstreamHealthService.list_healths(session, limit, offset,
                                                     status_filter, keyword)


@upstream_router.post("", status_code=status.HTTP_201_CREATED)
async def create_upstream(
    payload: UpstreamHealthCreate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await UpstreamHealthService.create_health(session, payload, request)


@upstream_router.get("/{health_id}")
async def get_upstream(
    health_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await UpstreamHealthService.get_health(session, health_id)


@upstream_router.patch("/{health_id}")
async def update_upstream(
    health_id: str, payload: UpstreamHealthUpdate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await UpstreamHealthService.update_health(session, health_id, payload, request)


@upstream_router.patch("/{health_id}/status")
async def report_upstream_status(
    health_id: str, payload: UpstreamHealthStatusUpdate, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await UpstreamHealthService.report_status(session, health_id, payload, request)


@upstream_router.delete("/{health_id}")
async def delete_upstream(
    health_id: str, request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await UpstreamHealthService.delete_health(session, health_id, request)
