"""网关路由规则仓储层。"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gateway_route import GatewayRoute


async def get_route(session: AsyncSession, route_id: str) -> GatewayRoute | None:
    result = await session.execute(select(GatewayRoute).where(GatewayRoute.id == route_id))
    return result.scalar_one_or_none()


async def get_route_by_pattern(session: AsyncSession, path_pattern: str) -> GatewayRoute | None:
    result = await session.execute(
        select(GatewayRoute).where(GatewayRoute.path_pattern == path_pattern)
    )
    return result.scalar_one_or_none()


async def list_routes(
    session: AsyncSession, limit: int = 100, offset: int = 0,
    status: str | None = None, keyword: str | None = None,
) -> list[GatewayRoute]:
    stmt = select(GatewayRoute).order_by(GatewayRoute.priority.asc(), GatewayRoute.created_at.desc())
    if status:
        stmt = stmt.where(GatewayRoute.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(GatewayRoute.path_pattern.like(like), GatewayRoute.upstream_url.like(like)))
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_routes(
    session: AsyncSession, status: str | None = None, keyword: str | None = None,
) -> int:
    stmt = select(func.count(GatewayRoute.id))
    if status:
        stmt = stmt.where(GatewayRoute.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(GatewayRoute.path_pattern.like(like), GatewayRoute.upstream_url.like(like)))
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def create_route(session: AsyncSession, route: GatewayRoute) -> GatewayRoute:
    session.add(route)
    await session.commit()
    await session.refresh(route)
    return route


async def update_route(session: AsyncSession, route: GatewayRoute) -> GatewayRoute:
    await session.commit()
    await session.refresh(route)
    return route


async def delete_route(session: AsyncSession, route: GatewayRoute) -> None:
    await session.delete(route)
    await session.commit()
