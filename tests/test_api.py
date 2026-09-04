"""SM API Gateway 领域测试：路由、代理白名单、鉴权、限流、访问日志。"""

import pytest
from fastapi.testclient import TestClient

from app import base
from app.main import VERSION, app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(base, "internal_api_key", lambda: "TEST")
    import app.main as m

    # 保存真实校验函数，供 fail-closed 用例恢复使用
    m._REAL_PORTAL_VALIDATE = m._call_portal_validate
    # 模拟已配置开发者门户：仅接受 smk_valid_ 前缀的真实密钥（哈希匹配由门户负责）
    monkeypatch.setattr(m, "_call_portal_validate", lambda key: key.startswith("smk_valid_"))
    base.reset_state()
    m._init()
    with TestClient(app) as c:
        c.headers["X-Internal-Token"] = "TEST"
        yield c


def _route(client, path="/api/orders", rate=100):
    return client.post("/api/gateway/routes", json={"path": path, "method": "GET", "upstream": "http://sm-erp:8100", "rate_limit_per_min": rate}).json()["id"]


def test_health_and_version(client):
    r = client.get("/health", headers={"X-Request-Id": "suite-test"})
    assert r.status_code == 200
    assert r.json()["version"] == VERSION


def test_route_crud(client):
    _route(client)
    assert client.post("/api/gateway/routes", json={"path": "/api/orders", "method": "GET", "upstream": "http://x"}).status_code == 409
    assert client.get("/api/gateway/routes").json()["total"] == 1
    route_id = client.get("/api/gateway/routes").json()["items"][0]["id"]
    assert client.delete(f"/api/gateway/routes/{route_id}").json()["deleted"] is True
    assert client.get("/api/gateway/routes").json()["total"] == 0


def test_proxy_requires_auth_key(client):
    _route(client)
    # 默认 auth_required=1，无 API Key → 401
    assert client.post("/api/gateway/proxy", json={"path": "/api/orders", "method": "GET"}).status_code == 401
    # 有效 Key（门户哈希匹配）→ 200 并记录访问日志
    resp = client.post("/api/gateway/proxy", json={"path": "/api/orders", "method": "GET"}, headers={"X-Api-Key": "smk_valid_key_1234567890"})
    assert resp.status_code == 200
    assert client.get("/api/gateway/requests").json()["total"] == 1
    # 无效 Key（门户哈希不匹配）→ 401
    assert client.post("/api/gateway/proxy", json={"path": "/api/orders", "method": "GET"}, headers={"X-Api-Key": "smk_forged_key_abcdefghijkl"}).status_code == 401


def test_proxy_fail_closed_without_portal(client, monkeypatch):
    """未配置开发者门户时网关必须 fail-closed：任何 X-Api-Key（含伪造 smk_ 前缀）一律拒绝。"""
    import app.main as m

    monkeypatch.delenv("SM_API_PORTAL_URL", raising=False)
    monkeypatch.setattr(m, "_call_portal_validate", m._REAL_PORTAL_VALIDATE)
    _route(client)
    for forged in ("smk_" + "a" * 30, "smk_forged_key_1234567890", "smk_x"):
        r = client.post("/api/gateway/proxy", json={"path": "/api/orders", "method": "GET"}, headers={"X-Api-Key": forged})
        assert r.status_code == 401, f"未配置门户时应拒绝伪造 Key {forged[:12]}..., got {r.status_code}"


def test_proxy_allowlist(client):
    _route(client)
    # 未注册路径 → 404（禁止任意路径代理）
    assert client.post("/api/gateway/proxy", json={"path": "/etc/passwd", "method": "GET"}, headers={"X-Api-Key": "smk_valid_key_1234567890"}).status_code == 404


def test_proxy_rate_limit(client):
    _route(client, rate=2)
    for _ in range(2):
        assert client.post("/api/gateway/proxy", json={"path": "/api/orders", "method": "GET"}, headers={"X-Api-Key": "smk_valid_key_1234567890"}).status_code == 200
    assert client.post("/api/gateway/proxy", json={"path": "/api/orders", "method": "GET"}, headers={"X-Api-Key": "smk_valid_key_1234567890"}).status_code == 429


def test_route_disable(client):
    route_id = _route(client)
    assert client.post(f"/api/gateway/routes/{route_id}/status", json={"enabled": 0}).json()["enabled"] == 0
    assert client.post("/api/gateway/proxy", json={"path": "/api/orders", "method": "GET"}, headers={"X-Api-Key": "smk_valid_key_1234567890"}).status_code == 404


def test_stats(client):
    _route(client)
    stats = client.get("/api/gateway/stats").json()
    assert stats["routes"] == 1
    assert stats["enabled_routes"] == 1


def test_manifest_and_crypto(client):
    assert client.get("/api/integration/manifest").json()["version"] == VERSION
    enc = client.post("/api/crypto/encrypt", json={"value": "x"}).json()["ciphertext"]
    assert client.post("/api/crypto/decrypt", json={"value": enc}).json()["plaintext"] == "x"


def test_write_requires_auth(client):
    del client.headers["X-Internal-Token"]
    assert client.post("/api/gateway/routes", json={"path": "/x", "method": "GET", "upstream": "http://x"}).status_code == 401
