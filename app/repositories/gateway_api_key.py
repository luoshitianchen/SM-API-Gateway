"""网关 API 密钥仓储层。"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gateway_api_key import GatewayApiKey


async def get_key(session: AsyncSession, key_id: str) -> GatewayApiKey | None:
    result = await session.execute(select(GatewayApiKey).where(GatewayApiKey.id == key_id))
    return result.scalar_one_or_none()


async def get_key_by_key_id(session: AsyncSession, public_key_id: str) -> GatewayApiKey | None:
    result = await session.execute(select(GatewayApiKey).where(GatewayApiKey.key_id == public_key_id))
    return result.scalar_one_or_none()


async def list_keys(
    session: AsyncSession, limit: int = 100, offset: int = 0,
    status: str | None = None, keyword: str | None = None,
) -> list[GatewayApiKey]:
    stmt = select(GatewayApiKey).order_by(GatewayApiKey.created_at.desc())
    if status:
        stmt = stmt.where(GatewayApiKey.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(GatewayApiKey.name.like(like), GatewayApiKey.owner.like(like)))
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_keys(
    session: AsyncSession, status: str | None = None, keyword: str | None = None,
) -> int:
    stmt = select(func.count(GatewayApiKey.id))
    if status:
        stmt = stmt.where(GatewayApiKey.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(GatewayApiKey.name.like(like), GatewayApiKey.owner.like(like)))
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def create_key(session: AsyncSession, key: GatewayApiKey) -> GatewayApiKey:
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return key


async def update_key(session: AsyncSession, key: GatewayApiKey) -> GatewayApiKey:
    await session.commit()
    await session.refresh(key)
    return key


async def delete_key(session: AsyncSession, key: GatewayApiKey) -> None:
    await session.delete(key)
    await session.commit()
