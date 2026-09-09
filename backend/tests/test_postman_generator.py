"""
Unit and Integration Tests for Postman Collection v2.1.0 Generator
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestPostmanGeneratorAndOpenAPI:
    def test_postman_and_openapi_generation(self):
        """Creates a test project with artifacts and tests OpenAPI & Postman exports."""
        # 1. Create project
        create_res = client.post("/projects/", json={
            "name": "Postman Test API",
            "brief": "A microservice for managing orders and inventory with REST APIs."
        })
        assert create_res.status_code == 200
        proj_id = create_res.json()["id"]

        # 2. Trigger generation
        gen_res = client.post(f"/projects/{proj_id}/generate")
        assert gen_res.status_code == 200

        # 3. Test OpenAPI spec export
        openapi_res = client.get(f"/projects/{proj_id}/openapi.json")
        assert openapi_res.status_code == 200
        openapi_data = openapi_res.json()
        assert openapi_data["openapi"] == "3.0.3"
        assert "paths" in openapi_data
        assert "components" in openapi_data

        # 4. Test Postman Collection JSON export
        postman_res = client.get(f"/projects/{proj_id}/postman-collection.json")
        assert postman_res.status_code == 200
        postman_data = postman_res.json()
        assert "info" in postman_data
        assert "schema" in postman_data["info"]
        assert "collection.json" in postman_data["info"]["schema"]
        assert "item" in postman_data
        assert len(postman_data["item"]) > 0
        assert "variable" in postman_data

        # Verify folder structure and test scripts
        first_folder = postman_data["item"][0]
        assert "name" in first_folder
        assert "item" in first_folder
        first_req = first_folder["item"][0]
        assert "request" in first_req
        assert "method" in first_req["request"]
        assert "url" in first_req["request"]
        assert "event" in first_req
        assert len(first_req["event"]) > 0

        # 5. Test Postman Generation POST endpoint
        gen_postman_res = client.post(f"/projects/{proj_id}/generate-postman")
        assert gen_postman_res.status_code == 200
        gen_postman_data = gen_postman_res.json()
        assert gen_postman_data["status"] == "success"
        assert gen_postman_data["folders_count"] > 0
