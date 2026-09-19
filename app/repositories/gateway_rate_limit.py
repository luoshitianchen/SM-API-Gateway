"""网关限流规则仓储层。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gateway_rate_limit import GatewayRateLimitRule


async def get_rule(session: AsyncSession, rule_id: str) -> GatewayRateLimitRule | None:
    result = await session.execute(select(GatewayRateLimitRule).where(GatewayRateLimitRule.id == rule_id))
    return result.scalar_one_or_none()


async def get_rule_by_name(session: AsyncSession, name: str) -> GatewayRateLimitRule | None:
    result = await session.execute(select(GatewayRateLimitRule).where(GatewayRateLimitRule.name == name))
    return result.scalar_one_or_none()


async def list_rules(
    session: AsyncSession, limit: int = 100, offset: int = 0,
    status: str | None = None, key_type: str | None = None, keyword: str | None = None,
) -> list[GatewayRateLimitRule]:
    stmt = select(GatewayRateLimitRule).order_by(GatewayRateLimitRule.created_at.desc())
    if status:
        stmt = stmt.where(GatewayRateLimitRule.status == status)
    if key_type:
        stmt = stmt.where(GatewayRateLimitRule.key_type == key_type)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(GatewayRateLimitRule.name.like(like))
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_rules(
    session: AsyncSession, status: str | None = None, key_type: str | None = None,
    keyword: str | None = None,
) -> int:
    stmt = select(func.count(GatewayRateLimitRule.id))
    if status:
        stmt = stmt.where(GatewayRateLimitRule.status == status)
    if key_type:
        stmt = stmt.where(GatewayRateLimitRule.key_type == key_type)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(GatewayRateLimitRule.name.like(like))
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def create_rule(session: AsyncSession, rule: GatewayRateLimitRule) -> GatewayRateLimitRule:
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def update_rule(session: AsyncSession, rule: GatewayRateLimitRule) -> GatewayRateLimitRule:
    await session.commit()
    await session.refresh(rule)
    return rule


async def delete_rule(session: AsyncSession, rule: GatewayRateLimitRule) -> None:
    await session.delete(rule)
    await session.commit()
