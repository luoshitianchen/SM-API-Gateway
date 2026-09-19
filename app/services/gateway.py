"""网关业务域服务层：路由 / 限流 / 密钥 / 上游健康全生命周期管理。"""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import internal_write_allowed, sm3_hex
from app.models.gateway_api_key import GatewayApiKey
from app.models.gateway_rate_limit import GatewayRateLimitRule
from app.models.gateway_route import GatewayRoute
from app.models.gateway_upstream_health import GatewayUpstreamHealth
from app.repositories import gateway_api_key as key_repo
from app.repositories import gateway_rate_limit as rule_repo
from app.repositories import gateway_route as route_repo
from app.repositories import gateway_upstream_health as health_repo
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
from app.services.audit import record_audit


def _require_write(request: Request) -> None:
    """写操作统一鉴权：校验内部写入令牌。"""
    if not internal_write_allowed(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "内部写入令牌无效")


# ═══════════════════════════════════════════════════════════
# 路由规则
# ═══════════════════════════════════════════════════════════

class RouteService:
    @staticmethod
    def _to_dict(r: GatewayRoute) -> dict:
        return {
            "id": r.id, "path_pattern": r.path_pattern, "upstream_url": r.upstream_url,
            "methods": r.methods, "status": r.status, "priority": r.priority,
            "description": r.description,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "updated_at": r.updated_at.isoformat() if r.updated_at else "",
        }

    @staticmethod
    async def list_routes(session: AsyncSession, limit: int, offset: int,
                          status_filter: str | None, keyword: str | None) -> dict:
        items = await route_repo.list_routes(session, limit=limit, offset=offset,
                                              status=status_filter, keyword=keyword)
        total = await route_repo.count_routes(session, status=status_filter, keyword=keyword)
        return {"total": total, "items": [RouteService._to_dict(r) for r in items]}

    @staticmethod
    async def get_route(session: AsyncSession, route_id: str) -> dict:
        route = await route_repo.get_route(session, route_id)
        if not route:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "路由规则不存在")
        return RouteService._to_dict(route)

    @staticmethod
    async def create_route(session: AsyncSession, payload: RouteCreate, request: Request) -> dict:
        _require_write(request)
        if await route_repo.get_route_by_pattern(session, payload.path_pattern):
            raise HTTPException(status.HTTP_409_CONFLICT, "路径模式已存在")
        route = GatewayRoute(
            id=str(uuid.uuid4()), path_pattern=payload.path_pattern,
            upstream_url=payload.upstream_url, methods=payload.methods,
            priority=payload.priority, description=payload.description, status="active",
        )
        route = await route_repo.create_route(session, route)
        await record_audit(session, "gateway.route.created", "internal",
                           f"path={payload.path_pattern}", request)
        return RouteService._to_dict(route)

    @staticmethod
    async def update_route(session: AsyncSession, route_id: str, payload: RouteUpdate,
                           request: Request) -> dict:
        _require_write(request)
        route = await route_repo.get_route(session, route_id)
        if not route:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "路由规则不存在")
        if payload.upstream_url is not None:
            route.upstream_url = payload.upstream_url
        if payload.methods is not None:
            route.methods = payload.methods
        if payload.priority is not None:
            route.priority = payload.priority
        if payload.description is not None:
            route.description = payload.description
        route = await route_repo.update_route(session, route)
        await record_audit(session, "gateway.route.updated", "internal",
                           f"route_id={route_id}", request)
        return RouteService._to_dict(route)

    @staticmethod
    async def update_status(session: AsyncSession, route_id: str, payload: RouteStatusUpdate,
                            request: Request) -> dict:
        _require_write(request)
        route = await route_repo.get_route(session, route_id)
        if not route:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "路由规则不存在")
        route.status = payload.status
        route = await route_repo.update_route(session, route)
        await record_audit(session, "gateway.route.status_changed", "internal",
                           f"route_id={route_id} status={payload.status}", request)
        return RouteService._to_dict(route)

    @staticmethod
    async def delete_route(session: AsyncSession, route_id: str, request: Request) -> dict:
        _require_write(request)
        route = await route_repo.get_route(session, route_id)
        if not route:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "路由规则不存在")
        await route_repo.delete_route(session, route)
        await record_audit(session, "gateway.route.deleted", "internal",
                           f"route_id={route_id}", request)
        return {"deleted": True, "id": route_id}


# ═══════════════════════════════════════════════════════════
# 限流规则
# ═══════════════════════════════════════════════════════════

class RateLimitRuleService:
    @staticmethod
    def _to_dict(r: GatewayRateLimitRule) -> dict:
        return {
            "id": r.id, "name": r.name, "key_type": r.key_type,
            "limit_rpm": r.limit_rpm, "burst": r.burst, "status": r.status,
            "description": r.description,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "updated_at": r.updated_at.isoformat() if r.updated_at else "",
        }

    @staticmethod
    async def list_rules(session: AsyncSession, limit: int, offset: int,
                         status_filter: str | None, key_type: str | None,
                         keyword: str | None) -> dict:
        items = await rule_repo.list_rules(session, limit=limit, offset=offset,
                                           status=status_filter, key_type=key_type, keyword=keyword)
        total = await rule_repo.count_rules(session, status=status_filter,
                                            key_type=key_type, keyword=keyword)
        return {"total": total, "items": [RateLimitRuleService._to_dict(r) for r in items]}

    @staticmethod
    async def get_rule(session: AsyncSession, rule_id: str) -> dict:
        rule = await rule_repo.get_rule(session, rule_id)
        if not rule:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "限流规则不存在")
        return RateLimitRuleService._to_dict(rule)

    @staticmethod
    async def create_rule(session: AsyncSession, payload: RateLimitRuleCreate,
                          request: Request) -> dict:
        _require_write(request)
        if await rule_repo.get_rule_by_name(session, payload.name):
            raise HTTPException(status.HTTP_409_CONFLICT, "规则名称已存在")
        rule = GatewayRateLimitRule(
            id=str(uuid.uuid4()), name=payload.name, key_type=payload.key_type,
            limit_rpm=payload.limit_rpm, burst=payload.burst,
            description=payload.description, status="active",
        )
        rule = await rule_repo.create_rule(session, rule)
        await record_audit(session, "gateway.ratelimit.created", "internal",
                           f"name={payload.name}", request)
        return RateLimitRuleService._to_dict(rule)

    @staticmethod
    async def update_rule(session: AsyncSession, rule_id: str, payload: RateLimitRuleUpdate,
                          request: Request) -> dict:
        _require_write(request)
        rule = await rule_repo.get_rule(session, rule_id)
        if not rule:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "限流规则不存在")
        if payload.limit_rpm is not None:
            rule.limit_rpm = payload.limit_rpm
        if payload.burst is not None:
            rule.burst = payload.burst
        if payload.description is not None:
            rule.description = payload.description
        rule = await rule_repo.update_rule(session, rule)
        await record_audit(session, "gateway.ratelimit.updated", "internal",
                           f"rule_id={rule_id}", request)
        return RateLimitRuleService._to_dict(rule)

    @staticmethod
    async def update_status(session: AsyncSession, rule_id: str, payload: RateLimitRuleStatusUpdate,
                            request: Request) -> dict:
        _require_write(request)
        rule = await rule_repo.get_rule(session, rule_id)
        if not rule:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "限流规则不存在")
        rule.status = payload.status
        rule = await rule_repo.update_rule(session, rule)
        await record_audit(session, "gateway.ratelimit.status_changed", "internal",
                           f"rule_id={rule_id} status={payload.status}", request)
        return RateLimitRuleService._to_dict(rule)

    @staticmethod
    async def delete_rule(session: AsyncSession, rule_id: str, request: Request) -> dict:
        _require_write(request)
        rule = await rule_repo.get_rule(session, rule_id)
        if not rule:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "限流规则不存在")
        await rule_repo.delete_rule(session, rule)
        await record_audit(session, "gateway.ratelimit.deleted", "internal",
                           f"rule_id={rule_id}", request)
        return {"deleted": True, "id": rule_id}


# ═══════════════════════════════════════════════════════════
# 网关密钥
# ═══════════════════════════════════════════════════════════

class ApiKeyService:
    @staticmethod
    def _to_dict(k: GatewayApiKey) -> dict:
        return {
            "id": k.id, "key_id": k.key_id, "name": k.name, "owner": k.owner,
            "status": k.status,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "description": k.description,
            "created_at": k.created_at.isoformat() if k.created_at else "",
            "updated_at": k.updated_at.isoformat() if k.updated_at else "",
        }

    @staticmethod
    async def list_keys(session: AsyncSession, limit: int, offset: int,
                        status_filter: str | None, keyword: str | None) -> dict:
        items = await key_repo.list_keys(session, limit=limit, offset=offset,
                                          status=status_filter, keyword=keyword)
        total = await key_repo.count_keys(session, status=status_filter, keyword=keyword)
        return {"total": total, "items": [ApiKeyService._to_dict(k) for k in items]}

    @staticmethod
    async def get_key(session: AsyncSession, key_id: str) -> dict:
        record = await key_repo.get_key(session, key_id)
        if not record:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "密钥不存在")
        return ApiKeyService._to_dict(record)

    @staticmethod
    async def create_key(session: AsyncSession, payload: ApiKeyCreate, request: Request) -> dict:
        _require_write(request)
        plain = secrets.token_urlsafe(32)
        public_id = f"gk_{secrets.token_hex(8)}"
        record = GatewayApiKey(
            id=str(uuid.uuid4()), key_id=public_id, key_hash=sm3_hex(plain),
            name=payload.name, owner=payload.owner,
            expires_at=datetime.now(UTC) + timedelta(days=payload.expires_in_days),
            description=payload.description, status="active",
        )
        record = await key_repo.create_key(session, record)
        await record_audit(session, "gateway.apikey.created", "internal",
                           f"key_id={public_id}", request)
        result = ApiKeyService._to_dict(record)
        # 明文密钥仅在创建时返回一次
        result["plain_key"] = plain
        return result

    @staticmethod
    async def update_key(session: AsyncSession, key_id: str, payload: ApiKeyUpdate,
                         request: Request) -> dict:
        _require_write(request)
        record = await key_repo.get_key(session, key_id)
        if not record:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "密钥不存在")
        if record.status == "revoked":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "已吊销密钥不可修改")
        if payload.name is not None:
            record.name = payload.name
        if payload.owner is not None:
            record.owner = payload.owner
        if payload.description is not None:
            record.description = payload.description
        record = await key_repo.update_key(session, record)
        await record_audit(session, "gateway.apikey.updated", "internal",
                           f"key_id={key_id}", request)
        return ApiKeyService._to_dict(record)

    @staticmethod
    async def update_status(session: AsyncSession, key_id: str, payload: ApiKeyStatusUpdate,
                            request: Request) -> dict:
        _require_write(request)
        record = await key_repo.get_key(session, key_id)
        if not record:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "密钥不存在")
        # 状态机：revoked 为终态，不可恢复为 active
        if record.status == "revoked" and payload.status == "active":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "已吊销密钥不可重新激活")
        record.status = payload.status
        record = await key_repo.update_key(session, record)
        await record_audit(session, "gateway.apikey.status_changed", "internal",
                           f"key_id={key_id} status={payload.status}", request)
        return ApiKeyService._to_dict(record)

    @staticmethod
    async def delete_key(session: AsyncSession, key_id: str, request: Request) -> dict:
        _require_write(request)
        record = await key_repo.get_key(session, key_id)
        if not record:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "密钥不存在")
        await key_repo.delete_key(session, record)
        await record_audit(session, "gateway.apikey.deleted", "internal",
                           f"key_id={key_id}", request)
        return {"deleted": True, "id": key_id}


# ═══════════════════════════════════════════════════════════
# 上游健康
# ═══════════════════════════════════════════════════════════

class UpstreamHealthService:
    @staticmethod
    def _to_dict(h: GatewayUpstreamHealth) -> dict:
        return {
            "id": h.id, "upstream_name": h.upstream_name, "upstream_url": h.upstream_url,
            "status": h.status,
            "last_check_at": h.last_check_at.isoformat() if h.last_check_at else None,
            "last_error": h.last_error, "consecutive_failures": h.consecutive_failures,
            "created_at": h.created_at.isoformat() if h.created_at else "",
            "updated_at": h.updated_at.isoformat() if h.updated_at else "",
        }

    @staticmethod
    async def list_healths(session: AsyncSession, limit: int, offset: int,
                           status_filter: str | None, keyword: str | None) -> dict:
        items = await health_repo.list_healths(session, limit=limit, offset=offset,
                                                status=status_filter, keyword=keyword)
        total = await health_repo.count_healths(session, status=status_filter, keyword=keyword)
        return {"total": total, "items": [UpstreamHealthService._to_dict(h) for h in items]}

    @staticmethod
    async def get_health(session: AsyncSession, health_id: str) -> dict:
        record = await health_repo.get_health(session, health_id)
        if not record:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "上游健康记录不存在")
        return UpstreamHealthService._to_dict(record)

    @staticmethod
    async def create_health(session: AsyncSession, payload: UpstreamHealthCreate,
                            request: Request) -> dict:
        _require_write(request)
        if await health_repo.get_health_by_name(session, payload.upstream_name):
            raise HTTPException(status.HTTP_409_CONFLICT, "上游名称已存在")
        record = GatewayUpstreamHealth(
            id=str(uuid.uuid4()), upstream_name=payload.upstream_name,
            upstream_url=payload.upstream_url, status="unknown",
        )
        record = await health_repo.create_health(session, record)
        await record_audit(session, "gateway.upstream.created", "internal",
                           f"upstream={payload.upstream_name}", request)
        return UpstreamHealthService._to_dict(record)

    @staticmethod
    async def update_health(session: AsyncSession, health_id: str, payload: UpstreamHealthUpdate,
                             request: Request) -> dict:
        _require_write(request)
        record = await health_repo.get_health(session, health_id)
        if not record:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "上游健康记录不存在")
        if payload.upstream_url is not None:
            record.upstream_url = payload.upstream_url
        record = await health_repo.update_health(session, record)
        await record_audit(session, "gateway.upstream.updated", "internal",
                           f"health_id={health_id}", request)
        return UpstreamHealthService._to_dict(record)

    @staticmethod
    async def report_status(session: AsyncSession, health_id: str,
                            payload: UpstreamHealthStatusUpdate, request: Request) -> dict:
        """探活回调：更新上游健康状态与失败计数。"""
        _require_write(request)
        record = await health_repo.get_health(session, health_id)
        if not record:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "上游健康记录不存在")
        record.status = payload.status
        record.last_check_at = datetime.now(UTC)
        record.last_error = payload.last_error
        if payload.status == "healthy":
            record.consecutive_failures = 0
        else:
            record.consecutive_failures += 1
        record = await health_repo.update_health(session, record)
        await record_audit(session, "gateway.upstream.status_reported", "internal",
                           f"health_id={health_id} status={payload.status}", request)
        return UpstreamHealthService._to_dict(record)

    @staticmethod
    async def delete_health(session: AsyncSession, health_id: str, request: Request) -> dict:
        _require_write(request)
        record = await health_repo.get_health(session, health_id)
        if not record:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "上游健康记录不存在")
        await health_repo.delete_health(session, record)
        await record_audit(session, "gateway.upstream.deleted", "internal",
                           f"health_id={health_id}", request)
        return {"deleted": True, "id": health_id}
