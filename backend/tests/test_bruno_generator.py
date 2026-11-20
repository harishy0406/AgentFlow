"""
Unit & Integration Tests for Bruno Git-Friendly API Collection Generator Engine
"""

import io
import zipfile
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.models import Project, ArtifactNode, ArtifactSection
from app.agents.bruno_generator import (
    _slugify,
    _format_bru_file,
    generate_bruno_collection,
    generate_bruno_zip,
)

client = TestClient(app)


class TestBrunoGeneratorUnit:
    def test_slugify(self):
        assert _slugify("FinTech UPI Switch") == "fintech-upi-switch"
        assert _slugify("") == "agentflow-app"

    def test_format_bru_file(self):
        content = _format_bru_file(
            name="Create User",
            method="POST",
            path="/api/v1/users",
            seq=1,
            body_dict={"name": "Alice", "role": "admin"},
        )
        assert "meta {" in content
        assert "name: Create User" in content
        assert "post {" in content
        assert "url: {{baseUrl}}/api/v1/users" in content
        assert "body: json" in content
        assert "body:json {" in content
        assert '"name": "Alice"' in content
        assert "assert {" in content
        assert "res.status: eq 201" in content


class TestBrunoGeneratorIntegration:
    def test_bruno_collection_json_and_zip_endpoints(self):
        db = next(get_db())
        project = Project(
            id=uuid4(),
            name="Bruno Gateway Demo App",
            brief="Testing git-friendly Bruno collection generator",
        )
        db.add(project)
        db.commit()

        api_node = ArtifactNode(
            project_id=project.id,
            artifact_type="API_SPEC",
            version=1,
            status="fresh",
        )
        db.add(api_node)
        db.commit()

        db.add(
            ArtifactSection(
                artifact_node_id=api_node.id,
                section_key="endpoints",
                content="""
                ### GET /api/v1/health - Health check
                ### POST /api/v1/orders - Create new order
                ### GET /api/v1/orders/{id} - Get order details
                """,
                content_hash="h_api",
            )
        )
        db.commit()

        # 1. JSON endpoint
        res = client.get(f"/projects/{project.id}/bruno-collection?format=json")
        assert res.status_code == 200
        data = res.json()
        assert data["project_id"] == str(project.id)
        assert data["collection_name"] == "Bruno Gateway Demo App API"
        assert data["requests_count"] >= 3
        assert "local" in data["environments"]
        assert "production" in data["environments"]

        files = data["files"]
        assert "bruno-gateway-demo-app-bruno/bruno.json" in files
        assert "bruno-gateway-demo-app-bruno/environments/local.bru" in files
        assert "bruno-gateway-demo-app-bruno/environments/production.bru" in files

        # 2. ZIP endpoint
        res_zip = client.get(f"/projects/{project.id}/bruno-collection?format=zip")
        assert res_zip.status_code == 200
        assert "application/zip" in res_zip.headers["content-type"]
        assert "bruno-gateway-demo-app-bruno-collection.zip" in res_zip.headers["content-disposition"]

        # Validate ZIP contents
        with zipfile.ZipFile(io.BytesIO(res_zip.content), "r") as zf:
            namelist = zf.namelist()
            assert "bruno-gateway-demo-app-bruno/bruno.json" in namelist
            assert "bruno-gateway-demo-app-bruno/collection.bru" in namelist

    def test_bruno_collection_404_for_missing_project(self):
        res = client.get(f"/projects/{uuid4()}/bruno-collection")
        assert res.status_code == 404
