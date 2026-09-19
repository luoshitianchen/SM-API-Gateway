"""网关业务域 Pydantic 模型：路由 / 限流 / 密钥 / 上游健康。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════
# 路由规则
# ═══════════════════════════════════════════════════════════

class RouteCreate(BaseModel):
    path_pattern: str = Field(min_length=1, max_length=256, pattern=r"^/")
    upstream_url: str = Field(min_length=1, max_length=512)
    methods: str = Field(default="GET,POST,PUT,PATCH,DELETE", max_length=64)
    priority: int = Field(default=100, ge=0, le=9999)
    description: str = Field(default="", max_length=2048)


class RouteUpdate(BaseModel):
    upstream_url: str | None = Field(default=None, max_length=512)
    methods: str | None = Field(default=None, max_length=64)
    priority: int | None = Field(default=None, ge=0, le=9999)
    description: str | None = Field(default=None, max_length=2048)


class RouteStatusUpdate(BaseModel):
    status: Literal["active", "disabled"]


# ═══════════════════════════════════════════════════════════
# 限流规则
# ═══════════════════════════════════════════════════════════

class RateLimitRuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")
    key_type: Literal["api_key", "ip", "path"] = "api_key"
    limit_rpm: int = Field(default=60, ge=1, le=100000)
    burst: int = Field(default=10, ge=0, le=10000)
    description: str = Field(default="", max_length=2048)


class RateLimitRuleUpdate(BaseModel):
    limit_rpm: int | None = Field(default=None, ge=1, le=100000)
    burst: int | None = Field(default=None, ge=0, le=10000)
    description: str | None = Field(default=None, max_length=2048)


class RateLimitRuleStatusUpdate(BaseModel):
    status: Literal["active", "disabled"]


# ═══════════════════════════════════════════════════════════
# 网关密钥
# ═══════════════════════════════════════════════════════════

class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    owner: str = Field(default="", max_length=128)
    expires_in_days: int = Field(default=365, ge=1, le=3650)
    description: str = Field(default="", max_length=2048)


class ApiKeyUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    owner: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2048)


class ApiKeyStatusUpdate(BaseModel):
    status: Literal["active", "revoked"]


# ═══════════════════════════════════════════════════════════
# 上游健康
# ═══════════════════════════════════════════════════════════

class UpstreamHealthCreate(BaseModel):
    upstream_name: str = Field(min_length=2, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")
    upstream_url: str = Field(min_length=1, max_length=512)


class UpstreamHealthUpdate(BaseModel):
    upstream_url: str | None = Field(default=None, max_length=512)


class UpstreamHealthStatusUpdate(BaseModel):
    status: Literal["healthy", "unhealthy", "unknown"]
    last_error: str = Field(default="", max_length=2048)
