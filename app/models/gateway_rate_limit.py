"""网关限流规则模型：按 API 密钥 / IP / 路径维度限流。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class GatewayRateLimitRule(Base):
    """限流规则：在指定键维度上限制每分钟请求数与突发量。"""

    __tablename__ = "gateway_rate_limit_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    key_type: Mapped[str] = mapped_column(String(16), default="api_key", index=True)
    limit_rpm: Mapped[int] = mapped_column(Integer, default=60)
    burst: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
