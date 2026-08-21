from fastapi.testclient import TestClient
from app.main import app


def test_health_and_security_headers():
    with TestClient(app) as client:
        response = client.get('/health', headers={'X-Request-Id': 'suite-test'})
        assert response.status_code == 200
        assert response.headers['X-Request-Id'] == 'suite-test'
        assert response.headers['X-Frame-Options'] == 'DENY'
        assert response.json()['version'] == '2.0.0'


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



def test_integration_manifest_contract():
    with TestClient(app) as client:
        response = client.get('/api/integration/manifest')
        assert response.status_code == 200
        payload = response.json()
        assert payload['service']
        assert payload['version'] == '2.0.0'
        assert '/api/ops/metrics' == payload['metrics_path']
        assert isinstance(payload['dependencies'], list)



def test_request_size_and_rate_limit_guards(monkeypatch):
    from app import main
    main.RATE_BUCKETS.clear()
    monkeypatch.setattr(main, 'MAX_REQUEST_BYTES', 4)
    monkeypatch.setattr(main, 'RATE_MAX_REQUESTS', 1)
    with TestClient(app) as client:
        oversized = client.post('/api/items', content='12345', headers={'content-type': 'application/json'})
        assert oversized.status_code == 413
        assert client.get('/health').status_code == 200
        limited = client.get('/health')
        assert limited.status_code == 429
        assert limited.headers['Retry-After']


def test_internal_write_token_is_enforced(monkeypatch):
    from app import main
    monkeypatch.setattr(main, 'INTERNAL_API_KEY', 'TOKEN')
    with TestClient(app) as client:
        blocked = client.post('/api/items', json={'name': 'blocked'})
        assert blocked.status_code == 403
        allowed = client.post('/api/items', headers={'X-Internal-Token': 'TOKEN'}, json={'name': 'allowed'})
        assert allowed.status_code == 201
