from fastapi.testclient import TestClient
from app.main import app


def test_health_and_security_headers():
    with TestClient(app) as client:
        response = client.get('/health', headers={'X-Request-Id': 'suite-test'})
        assert response.status_code == 200
        assert response.headers['X-Request-Id'] == 'suite-test'
        assert response.headers['X-Frame-Options'] == 'DENY'
        assert response.json()['version'] == '1.0.0'


def test_overview_and_item_lifecycle():
    with TestClient(app) as client:
        overview = client.get('/api/overview').json()
        assert overview['total'] >= 2
        created = client.post('/api/items', json={'name': '企业级测试资源', 'owner': '测试部', 'priority': 'P2'}).json()
        assert created['status'] == 'active'
        updated = client.patch(f"/api/items/{created['id']}/status?item_status=review")
        assert updated.status_code == 200
        assert updated.json()['status'] == 'review'


def test_ops_metrics():
    with TestClient(app) as client:
        client.get('/health')
        metrics = client.get('/api/ops/metrics')
        assert metrics.status_code == 200
        assert metrics.json()['requests_total'] >= 1
