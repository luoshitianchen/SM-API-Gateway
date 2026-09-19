"""网关路由规则模型：将请求路径映射到上游服务地址。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class GatewayRoute(Base):
    """路由规则：path_pattern → upstream_url 的转发映射。"""

    __tablename__ = "gateway_routes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    path_pattern: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    upstream_url: Mapped[str] = mapped_column(String(512), nullable=False)
    methods: Mapped[str] = mapped_column(String(64), default="GET,POST,PUT,PATCH,DELETE")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
