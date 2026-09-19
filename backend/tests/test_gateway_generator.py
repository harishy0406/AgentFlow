import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.models import Project, ArtifactNode, ArtifactSection
from app.database import get_db
from app.agents.gateway_generator import generate_all_gateway_configs


def test_gateway_generator_direct_logic():
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="FinTech Payments Gateway",
        brief="High-throughput payment gateway with ISO20022 message conversion.",
    )
    db.add(project)

    node = ArtifactNode(
        id=uuid4(),
        project_id=project.id,
        artifact_type="API_SPEC",
        version=1,
        status="fresh",
    )
    db.add(node)

    section = ArtifactSection(
        id=uuid4(),
        artifact_node_id=node.id,
        section_key="endpoints",
        content="""| Method | Endpoint | Description |
|---|---|---|
| POST | /api/v1/payments/charge | Process credit card charge |
| GET | /api/v1/payments/{id} | Get transaction receipt |
| POST | /api/v1/refunds | Issue refund |""",
        content_hash="hash_payments_123",
    )
    db.add(section)
    db.commit()
    db.refresh(project)

    try:
        catalog = generate_all_gateway_configs(str(project.id), db)

        assert catalog.project_id == project.id
        assert catalog.project_name == project.name
        assert set(catalog.available_targets) == {"kong", "nginx", "envoy", "traefik"}

        # Kong Checks
        kong = catalog.configs["kong"]
        assert kong.filename == "kong.yml"
        assert "_format_version: \"3.0\"" in kong.content
        assert "rate-limiting" in kong.content
        assert "key-auth" in kong.content
        assert "/api/v1/payments/charge" in kong.content

        # Nginx Checks
        nginx = catalog.configs["nginx"]
        assert nginx.filename == "nginx.conf"
        assert "limit_req_zone" in nginx.content
        assert "upstream" in nginx.content
        assert "X-Frame-Options" in nginx.content

        # Envoy Checks
        envoy = catalog.configs["envoy"]
        assert envoy.filename == "envoy.yaml"
        assert "http_connection_manager" in envoy.content
        assert "ROUND_ROBIN" in envoy.content

        # Traefik Checks
        traefik = catalog.configs["traefik"]
        assert traefik.filename == "traefik.yml"
        assert "PathPrefix" in traefik.content
        assert "rateLimit" in traefik.content

        assert "# API Gateway Policies Catalog" in catalog.summary_markdown
    finally:
        db.delete(project)
        db.commit()


def test_gateway_api_endpoints():
    client = TestClient(app)
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="Telemetry Streamer",
        brief="IoT telemetry pipeline and sensor state aggregator.",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    try:
        # 1. GET /projects/{id}/gateway-configs
        res = client.get(f"/projects/{project.id}/gateway-configs")
        assert res.status_code == 200
        data = res.json()
        assert len(data["available_targets"]) == 4
        assert "kong" in data["configs"]

        # 2. Download Kong Config
        res_kong = client.get(f"/projects/{project.id}/gateway-configs/kong/download")
        assert res_kong.status_code == 200
        assert "kong.yml" in res_kong.headers["content-disposition"]
        assert "_format_version: \"3.0\"" in res_kong.text

        # 3. Download Nginx Config
        res_nginx = client.get(f"/projects/{project.id}/gateway-configs/nginx/download")
        assert res_nginx.status_code == 200
        assert "nginx.conf" in res_nginx.headers["content-disposition"]
        assert "worker_processes" in res_nginx.text

        # 4. Invalid target (404)
        res_bad_target = client.get(f"/projects/{project.id}/gateway-configs/caddy/download")
        assert res_bad_target.status_code == 404

        # 5. Invalid project (404)
        random_id = uuid4()
        res_bad_proj = client.get(f"/projects/{random_id}/gateway-configs")
        assert res_bad_proj.status_code == 404
    finally:
        db.delete(project)
        db.commit()
