"""安全回归测试：openapi 关闭、PUBLIC_PATH_PREFIXES GET 放行、写操作鉴权。"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_openapi_schema_disabled(client):
    """/openapi.json 不得暴露 API 结构（信息泄露修复）。"""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_docs_ui_disabled(client):
    """/docs 与 /redoc 不得暴露。"""
    assert (await client.get("/docs")).status_code == 404
    assert (await client.get("/redoc")).status_code == 404


@pytest.mark.asyncio
async def test_public_business_get_without_token(client):
    """业务域 GET 读操作按 PUBLIC_PATH_PREFIXES 放行（设计意图）。"""
    resp = await client.get("/api/gateway/routes")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_business_write_without_token_rejected(client):
    """业务域写操作不带内部令牌必须被服务层拒绝（403）。"""
    resp = await client.delete("/api/gateway/routes/probe-nonexistent")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_public_path_get_without_token_rejected(client):
    """不在 PUBLIC_PATH_PREFIXES 的业务 GET 不带令牌必须 401。"""
    resp = await client.get("/api/items")
    assert resp.status_code == 401
