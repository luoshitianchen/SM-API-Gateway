"""上游健康状态仓储层。"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gateway_upstream_health import GatewayUpstreamHealth


async def get_health(session: AsyncSession, health_id: str) -> GatewayUpstreamHealth | None:
    result = await session.execute(select(GatewayUpstreamHealth).where(GatewayUpstreamHealth.id == health_id))
    return result.scalar_one_or_none()


async def get_health_by_name(session: AsyncSession, upstream_name: str) -> GatewayUpstreamHealth | None:
    result = await session.execute(
        select(GatewayUpstreamHealth).where(GatewayUpstreamHealth.upstream_name == upstream_name)
    )
    return result.scalar_one_or_none()


async def list_healths(
    session: AsyncSession, limit: int = 100, offset: int = 0,
    status: str | None = None, keyword: str | None = None,
) -> list[GatewayUpstreamHealth]:
    stmt = select(GatewayUpstreamHealth).order_by(GatewayUpstreamHealth.created_at.desc())
    if status:
        stmt = stmt.where(GatewayUpstreamHealth.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(GatewayUpstreamHealth.upstream_name.like(like),
                GatewayUpstreamHealth.upstream_url.like(like))
        )
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_healths(
    session: AsyncSession, status: str | None = None, keyword: str | None = None,
) -> int:
    stmt = select(func.count(GatewayUpstreamHealth.id))
    if status:
        stmt = stmt.where(GatewayUpstreamHealth.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(GatewayUpstreamHealth.upstream_name.like(like),
                GatewayUpstreamHealth.upstream_url.like(like))
        )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def create_health(session: AsyncSession, health: GatewayUpstreamHealth) -> GatewayUpstreamHealth:
    session.add(health)
    await session.commit()
    await session.refresh(health)
    return health


async def update_health(session: AsyncSession, health: GatewayUpstreamHealth) -> GatewayUpstreamHealth:
    await session.commit()
    await session.refresh(health)
    return health


async def delete_health(session: AsyncSession, health: GatewayUpstreamHealth) -> None:
    await session.delete(health)
    await session.commit()
