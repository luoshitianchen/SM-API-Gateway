"""网关业务域深化测试：路由规则 / 限流规则 / 密钥 / 上游健康。"""
from __future__ import annotations

H = {"X-Internal-Token": "test-internal-key-12345"}


# ═══════════════════════════════════════════════════════════
# 路由规则
# ═══════════════════════════════════════════════════════════

class TestGatewayRoutes:
    async def test_create_route_success(self, client):
        resp = await client.post("/api/gateway/routes", json={
            "path_pattern": "/api/v1/users/*", "upstream_url": "http://iam:8000",
            "priority": 10, "description": "用户服务路由",
        }, headers=H)
        assert resp.status_code == 201
        data = resp.json()
        assert data["path_pattern"] == "/api/v1/users/*"
        assert data["status"] == "active"

    async def test_create_route_duplicate_pattern(self, client):
        await client.post("/api/gateway/routes", json={
            "path_pattern": "/api/v1/dup/*", "upstream_url": "http://x:8000",
        }, headers=H)
        resp = await client.post("/api/gateway/routes", json={
            "path_pattern": "/api/v1/dup/*", "upstream_url": "http://y:8000",
        }, headers=H)
        assert resp.status_code == 409

    async def test_list_routes_read_without_token(self, client):
        # 读操作放行：无令牌 GET 应成功
        resp = await client.get("/api/gateway/routes")
        assert resp.status_code == 200
        assert "total" in resp.json()

    async def test_create_route_requires_token(self, client):
        # 写操作需令牌：无令牌 POST 应被服务层拦截
        resp = await client.post("/api/gateway/routes", json={
            "path_pattern": "/api/v1/notoken/*", "upstream_url": "http://x:8000",
        })
        assert resp.status_code == 403

    async def test_get_route_by_id(self, client):
        create = await client.post("/api/gateway/routes", json={
            "path_pattern": "/api/v1/getbyid/*", "upstream_url": "http://x:8000",
        }, headers=H)
        rid = create.json()["id"]
        resp = await client.get(f"/api/gateway/routes/{rid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == rid

    async def test_get_route_not_found(self, client):
        resp = await client.get("/api/gateway/routes/nonexistent")
        assert resp.status_code == 404

    async def test_update_route(self, client):
        create = await client.post("/api/gateway/routes", json={
            "path_pattern": "/api/v1/upd/*", "upstream_url": "http://old:8000",
        }, headers=H)
        rid = create.json()["id"]
        resp = await client.patch(f"/api/gateway/routes/{rid}", json={
            "upstream_url": "http://new:9000", "priority": 50,
        }, headers=H)
        assert resp.status_code == 200
        assert resp.json()["upstream_url"] == "http://new:9000"
        assert resp.json()["priority"] == 50

    async def test_update_route_status_disable(self, client):
        create = await client.post("/api/gateway/routes", json={
            "path_pattern": "/api/v1/status/*", "upstream_url": "http://x:8000",
        }, headers=H)
        rid = create.json()["id"]
        resp = await client.patch(f"/api/gateway/routes/{rid}/status",
                                  json={"status": "disabled"}, headers=H)
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    async def test_list_routes_filter_by_status(self, client):
        await client.post("/api/gateway/routes", json={
            "path_pattern": "/api/v1/filter/*", "upstream_url": "http://x:8000",
        }, headers=H)
        resp = await client.get("/api/gateway/routes?status=active")
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["status"] == "active"

    async def test_delete_route(self, client):
        create = await client.post("/api/gateway/routes", json={
            "path_pattern": "/api/v1/del/*", "upstream_url": "http://x:8000",
        }, headers=H)
        rid = create.json()["id"]
        resp = await client.delete(f"/api/gateway/routes/{rid}", headers=H)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


# ═══════════════════════════════════════════════════════════
# 限流规则
# ═══════════════════════════════════════════════════════════

class TestRateLimitRules:
    async def test_create_rule_success(self, client):
        resp = await client.post("/api/gateway/rate-rules", json={
            "name": "rule-normal", "key_type": "api_key",
            "limit_rpm": 120, "burst": 20,
        }, headers=H)
        assert resp.status_code == 201
        assert resp.json()["name"] == "rule-normal"
        assert resp.json()["limit_rpm"] == 120

    async def test_create_rule_duplicate_name(self, client):
        await client.post("/api/gateway/rate-rules", json={
            "name": "rule-dup", "limit_rpm": 60,
        }, headers=H)
        resp = await client.post("/api/gateway/rate-rules", json={
            "name": "rule-dup", "limit_rpm": 100,
        }, headers=H)
        assert resp.status_code == 409

    async def test_list_rules_read_without_token(self, client):
        resp = await client.get("/api/gateway/rate-rules")
        assert resp.status_code == 200
        assert "total" in resp.json()

    async def test_create_rule_requires_token(self, client):
        resp = await client.post("/api/gateway/rate-rules", json={
            "name": "rule-notoken", "limit_rpm": 60,
        })
        assert resp.status_code == 403

    async def test_update_rule(self, client):
        create = await client.post("/api/gateway/rate-rules", json={
            "name": "rule-upd", "limit_rpm": 60, "burst": 5,
        }, headers=H)
        rid = create.json()["id"]
        resp = await client.patch(f"/api/gateway/rate-rules/{rid}", json={
            "limit_rpm": 300, "burst": 50,
        }, headers=H)
        assert resp.status_code == 200
        assert resp.json()["limit_rpm"] == 300

    async def test_update_rule_status(self, client):
        create = await client.post("/api/gateway/rate-rules", json={
            "name": "rule-status", "limit_rpm": 60,
        }, headers=H)
        rid = create.json()["id"]
        resp = await client.patch(f"/api/gateway/rate-rules/{rid}/status",
                                  json={"status": "disabled"}, headers=H)
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    async def test_delete_rule(self, client):
        create = await client.post("/api/gateway/rate-rules", json={
            "name": "rule-del", "limit_rpm": 60,
        }, headers=H)
        rid = create.json()["id"]
        resp = await client.delete(f"/api/gateway/rate-rules/{rid}", headers=H)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


# ═══════════════════════════════════════════════════════════
# 网关密钥
# ═══════════════════════════════════════════════════════════

class TestApiKeys:
    async def test_create_key_returns_plain_once(self, client):
        resp = await client.post("/api/gateway/api-keys", json={
            "name": "支付密钥", "owner": "支付团队",
        }, headers=H)
        assert resp.status_code == 201
        data = resp.json()
        assert "plain_key" in data
        assert len(data["plain_key"]) > 0
        assert data["status"] == "active"

    async def test_get_key_does_not_leak_plain(self, client):
        create = await client.post("/api/gateway/api-keys", json={
            "name": "查询密钥", "owner": "测试",
        }, headers=H)
        kid = create.json()["id"]
        resp = await client.get(f"/api/gateway/api-keys/{kid}")
        assert resp.status_code == 200
        assert "plain_key" not in resp.json()

    async def test_list_keys_read_without_token(self, client):
        resp = await client.get("/api/gateway/api-keys")
        assert resp.status_code == 200
        assert "total" in resp.json()

    async def test_revoked_key_cannot_reactivate(self, client):
        create = await client.post("/api/gateway/api-keys", json={
            "name": "吊销密钥", "owner": "测试",
        }, headers=H)
        kid = create.json()["id"]
        # 吊销
        await client.patch(f"/api/gateway/api-keys/{kid}/status",
                           json={"status": "revoked"}, headers=H)
        # 尝试恢复 active → 状态机拒绝
        resp = await client.patch(f"/api/gateway/api-keys/{kid}/status",
                                   json={"status": "active"}, headers=H)
        assert resp.status_code == 400

    async def test_revoked_key_cannot_update(self, client):
        create = await client.post("/api/gateway/api-keys", json={
            "name": "吊销后改", "owner": "测试",
        }, headers=H)
        kid = create.json()["id"]
        await client.patch(f"/api/gateway/api-keys/{kid}/status",
                           json={"status": "revoked"}, headers=H)
        resp = await client.patch(f"/api/gateway/api-keys/{kid}",
                                   json={"name": "新名称"}, headers=H)
        assert resp.status_code == 400

    async def test_delete_key(self, client):
        create = await client.post("/api/gateway/api-keys", json={
            "name": "删除密钥", "owner": "测试",
        }, headers=H)
        kid = create.json()["id"]
        resp = await client.delete(f"/api/gateway/api-keys/{kid}", headers=H)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


# ═══════════════════════════════════════════════════════════
# 上游健康
# ═══════════════════════════════════════════════════════════

class TestUpstreamHealth:
    async def test_create_upstream_success(self, client):
        resp = await client.post("/api/gateway/upstreams", json={
            "upstream_name": "user-svc", "upstream_url": "http://user-svc:8000",
        }, headers=H)
        assert resp.status_code == 201
        assert resp.json()["status"] == "unknown"

    async def test_create_upstream_duplicate_name(self, client):
        await client.post("/api/gateway/upstreams", json={
            "upstream_name": "dup-svc", "upstream_url": "http://x:8000",
        }, headers=H)
        resp = await client.post("/api/gateway/upstreams", json={
            "upstream_name": "dup-svc", "upstream_url": "http://y:8000",
        }, headers=H)
        assert resp.status_code == 409

    async def test_list_upstreams_read_without_token(self, client):
        resp = await client.get("/api/gateway/upstreams")
        assert resp.status_code == 200
        assert "total" in resp.json()

    async def test_report_unhealthy_increments_failures(self, client):
        create = await client.post("/api/gateway/upstreams", json={
            "upstream_name": "flaky-svc", "upstream_url": "http://flaky:8000",
        }, headers=H)
        hid = create.json()["id"]
        resp = await client.patch(f"/api/gateway/upstreams/{hid}/status",
                                   json={"status": "unhealthy", "last_error": "超时"},
                                   headers=H)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["consecutive_failures"] == 1

    async def test_report_healthy_resets_failures(self, client):
        create = await client.post("/api/gateway/upstreams", json={
            "upstream_name": "recover-svc", "upstream_url": "http://recover:8000",
        }, headers=H)
        hid = create.json()["id"]
        await client.patch(f"/api/gateway/upstreams/{hid}/status",
                           json={"status": "unhealthy", "last_error": "err"}, headers=H)
        await client.patch(f"/api/gateway/upstreams/{hid}/status",
                           json={"status": "unhealthy", "last_error": "err"}, headers=H)
        resp = await client.patch(f"/api/gateway/upstreams/{hid}/status",
                                   json={"status": "healthy", "last_error": ""}, headers=H)
        assert resp.status_code == 200
        assert resp.json()["consecutive_failures"] == 0
        assert resp.json()["status"] == "healthy"

    async def test_delete_upstream(self, client):
        create = await client.post("/api/gateway/upstreams", json={
            "upstream_name": "del-svc", "upstream_url": "http://del:8000",
        }, headers=H)
        hid = create.json()["id"]
        resp = await client.delete(f"/api/gateway/upstreams/{hid}", headers=H)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
