import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agents.api_sandbox import _match_route_pattern, _synthesize_mock_response

client = TestClient(app)


def test_match_route_pattern():
    assert _match_route_pattern("/api/v1/users", "/api/v1/users") is True
    assert _match_route_pattern("/api/v1/users/{id}", "/api/v1/users/42") is True
    assert _match_route_pattern("/api/v1/users/{id}", "/api/v1/users/abc-123") is True
    assert _match_route_pattern("/api/v1/users/{id}/orders", "/api/v1/users/42/orders") is True
    assert _match_route_pattern("/api/v1/users/{id}", "/api/v1/products/42") is False


def test_synthesize_mock_response():
    schemas = {
        "User": {"id": "int", "email": "str", "is_active": "bool"},
        "Order": {"id": "int", "total": "float", "status": "str"}
    }
    
    # GET collection
    res_list = _synthesize_mock_response("GET", "/api/v1/users", schemas)
    assert "items" in res_list
    assert res_list["total"] == 3
    assert len(res_list["items"]) == 3
    assert "email" in res_list["items"][0]

    # GET detail
    res_detail = _synthesize_mock_response("GET", "/api/v1/users/42", schemas)
    assert "id" in res_detail
    assert res_detail["is_active"] is True

    # POST create
    res_create = _synthesize_mock_response("POST", "/api/v1/orders", schemas, body={"total": 99.99})
    assert res_create["total"] == 99.99
    assert "id" in res_create

    # DELETE
    res_delete = _synthesize_mock_response("DELETE", "/api/v1/users/42", schemas)
    assert res_delete["status"] == "success"
    assert "deleted_id" in res_delete


def test_mock_api_endpoints_integration():
    # 1. Create a project and generate contracts
    p_res = client.post("/projects/", json={
        "name": "E-Commerce Mock Engine Service",
        "brief": "Full REST API with user management, orders, inventory catalog, and authentication."
    })
    assert p_res.status_code == 200
    p_id = p_res.json()["id"]

    gen_res = client.post(f"/projects/{p_id}/generate")
    assert gen_res.status_code == 200

    # 2. Fetch mock routes
    routes_res = client.get(f"/projects/{p_id}/mock-routes")
    assert routes_res.status_code == 200
    routes = routes_res.json()
    assert isinstance(routes, list)
    assert len(routes) > 0
    assert any("method" in r and "path" in r for r in routes)

    sample_route = routes[0]
    method = sample_route["method"]
    path = sample_route["path"]

    # 3. Execute mock API call against first route
    call_res = client.post(f"/projects/{p_id}/mock-api", json={
        "method": method,
        "path": path,
        "body": {"test_key": "test_value"} if method in ["POST", "PUT"] else None
    })
    assert call_res.status_code == 200
    data = call_res.json()

    assert "status_code" in data
    assert "status_text" in data
    assert "latency_ms" in data
    assert "response_body" in data
    assert "response_headers" in data
    assert data["matched_contract"] is True
    assert data["path"] == "/" + path.strip("/")
