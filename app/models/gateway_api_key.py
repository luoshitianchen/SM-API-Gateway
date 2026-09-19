"""网关 API 密钥模型：客户端调用网关的身份凭证。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class GatewayApiKey(Base):
    """网关密钥：存储 key_id 与 key_hash，明文密钥仅在创建时返回一次。"""

    __tablename__ = "gateway_api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    key_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    owner: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
