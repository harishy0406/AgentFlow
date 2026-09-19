import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.models import Project, ArtifactNode, ArtifactSection
from app.database import get_db
from app.agents.adr_generator import generate_project_adrs


def test_adr_generator_direct_logic():
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="Crypto Payment Gateway",
        brief="Non-custodial cryptocurrency payment gateway with webhook callbacks and transaction settlement.",
    )
    db.add(project)

    node = ArtifactNode(
        id=uuid4(),
        project_id=project.id,
        artifact_type="DB_SCHEMA",
        version=1,
        status="fresh",
    )
    db.add(node)

    section = ArtifactSection(
        id=uuid4(),
        artifact_node_id=node.id,
        section_key="schema_sql",
        content="CREATE TABLE settlements (id UUID PRIMARY KEY, amount NUMERIC, tx_hash VARCHAR);",
        content_hash="hash_settle_123",
    )
    db.add(section)
    db.commit()
    db.refresh(project)

    try:
        catalog = generate_project_adrs(str(project.id), db)

        assert catalog.project_id == project.id
        assert catalog.project_name == project.name
        assert catalog.total_adrs == 5
        assert len(catalog.adrs) == 5

        # Check ADR-0001
        adr1 = catalog.adrs[0]
        assert adr1.id == "ADR-0001"
        assert "PostgreSQL" in adr1.title
        assert adr1.status == "ACCEPTED"
        assert len(adr1.considered_options) >= 2
        assert "## Context and Problem Statement" in adr1.markdown_content

        # Check ADR-0002
        adr2 = catalog.adrs[1]
        assert adr2.id == "ADR-0002"
        assert "DAG" in adr2.title

        # Check master index
        assert "# Architecture Decision Log" in catalog.index_markdown
        assert "ADR-0001" in catalog.index_markdown
        assert "ADR-0005" in catalog.index_markdown
    finally:
        db.delete(project)
        db.commit()


def test_adr_api_endpoints():
    client = TestClient(app)
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="Logistics Routing Core",
        brief="Autonomous delivery route optimization platform with real-time GPS telemetry.",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    try:
        # 1. GET /projects/{id}/adrs
        res = client.get(f"/projects/{project.id}/adrs")
        assert res.status_code == 200
        data = res.json()
        assert data["project_name"] == "Logistics Routing Core"
        assert data["total_adrs"] == 5
        assert len(data["adrs"]) == 5

        # 2. GET /projects/{id}/adrs/ADR-0001/markdown
        res_md = client.get(f"/projects/{project.id}/adrs/ADR-0001/markdown")
        assert res_md.status_code == 200
        assert "text/markdown" in res_md.headers["content-type"]
        assert "attachment; filename=" in res_md.headers["content-disposition"]
        assert "# ADR-0001" in res_md.text

        # 3. Case-insensitive ADR ID check (adr-0002)
        res_md2 = client.get(f"/projects/{project.id}/adrs/adr-0002/markdown")
        assert res_md2.status_code == 200
        assert "# ADR-0002" in res_md2.text

        # 4. POST /projects/{id}/generate-adrs
        res_post = client.post(f"/projects/{project.id}/generate-adrs")
        assert res_post.status_code == 200
        assert res_post.json()["total_adrs"] == 5

        # 5. Non-existent ADR ID (404)
        res_bad_adr = client.get(f"/projects/{project.id}/adrs/ADR-9999/markdown")
        assert res_bad_adr.status_code == 404

        # 6. Non-existent Project ID (404)
        random_id = uuid4()
        res_bad_proj = client.get(f"/projects/{random_id}/adrs")
        assert res_bad_proj.status_code == 404

    finally:
        db.delete(project)
        db.commit()
