"""上游服务健康状态模型：记录网关对上游的探活结果。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class GatewayUpstreamHealth(Base):
    """上游健康：持续追踪上游服务可达性与失败计数。"""

    __tablename__ = "gateway_upstream_health"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    upstream_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    upstream_url: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="unknown", index=True)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
