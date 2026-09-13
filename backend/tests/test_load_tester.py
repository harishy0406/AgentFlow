import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agents.load_tester import _generate_performance_recommendations, execute_project_load_test

client = TestClient(app)


def test_generate_performance_recommendations():
    schemas = {"User": {"id": "int"}, "Order": {"id": "int"}}
    recs = _generate_performance_recommendations(
        endpoint="/api/v1/orders",
        method="GET",
        p95_ms=125.0,
        rps=350.0,
        schemas=schemas
    )
    assert len(recs) >= 3
    categories = [r["category"] for r in recs]
    assert "CACHING" in categories
    assert "DATABASE" in categories
    assert "GATEWAY" in categories


def test_load_testing_api_integration():
    # 1. Create a project
    p_res = client.post("/projects/", json={
        "name": "High Throughput Gateway",
        "brief": "API Gateway serving 5,000 requests/sec with caching."
    })
    assert p_res.status_code == 200
    p_id = p_res.json()["id"]

    client.post(f"/projects/{p_id}/generate")

    # 2. Trigger synthetic load test
    load_res = client.post(f"/projects/{p_id}/load-test", json={
        "target_endpoint": "/api/v1/orders",
        "method": "GET",
        "virtual_users": 100,
        "duration_seconds": 5,
        "ramp_up_seconds": 1
    })
    assert load_res.status_code == 200
    data = load_res.json()

    assert data["project_id"] == p_id
    assert data["virtual_users"] == 100
    assert data["total_requests"] > 0
    assert data["requests_per_sec"] > 0
    assert "latencies" in data
    assert data["latencies"]["p50_ms"] > 0
    assert data["latencies"]["p95_ms"] >= data["latencies"]["p50_ms"]
    assert "status_distribution" in data
    assert len(data["recommendations"]) > 0
