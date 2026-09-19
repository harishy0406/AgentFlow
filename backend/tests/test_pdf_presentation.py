import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.models import Project, ArtifactNode, ArtifactSection
from app.database import get_db
from app.reports.pdf_presentation import generate_project_presentation_pdf


def test_pdf_presentation_direct_generation():
    db = next(get_db())

    # Create test project with artifacts
    project = Project(
        id=uuid4(),
        name="FinTech Escrow Engine",
        brief="Design a fault-tolerant multi-party escrow platform with milestone tracking and automated payouts.",
    )
    db.add(project)

    # Add sample artifact node
    node_db = ArtifactNode(
        id=uuid4(),
        project_id=project.id,
        artifact_type="DB_SCHEMA",
        version=1,
        status="fresh",
    )
    db.add(node_db)

    section_db = ArtifactSection(
        id=uuid4(),
        artifact_node_id=node_db.id,
        section_key="schema_sql",
        content="""CREATE TABLE escrows (
            id UUID PRIMARY KEY,
            buyer_id UUID NOT NULL,
            seller_id UUID NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            status VARCHAR(32) NOT NULL
        );
        CREATE TABLE milestones (
            id UUID PRIMARY KEY,
            escrow_id UUID REFERENCES escrows(id),
            title VARCHAR(128) NOT NULL,
            completed BOOLEAN DEFAULT FALSE
        );""",
        content_hash="hash_db_123",
    )
    db.add(section_db)

    # Add API_SPEC node
    node_api = ArtifactNode(
        id=uuid4(),
        project_id=project.id,
        artifact_type="API_SPEC",
        version=1,
        status="fresh",
    )
    db.add(node_api)

    section_api = ArtifactSection(
        id=uuid4(),
        artifact_node_id=node_api.id,
        section_key="routes",
        content="""| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/escrows` | Create new escrow contract |
| GET | `/api/v1/escrows/{id}` | Fetch escrow status and balance |
| POST | `/api/v1/escrows/{id}/release` | Release funds to vendor |""",
        content_hash="hash_api_123",
    )
    db.add(section_api)

    db.commit()
    db.refresh(project)

    try:
        # Generate PDF
        pdf_bytes = generate_project_presentation_pdf(str(project.id), db)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 2000
        # Standard PDF binary file signature
        assert pdf_bytes.startswith(b"%PDF-1.")
    finally:
        db.delete(project)
        db.commit()


def test_pdf_presentation_endpoints():
    client = TestClient(app)
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="HealthTech Telehealth Suite",
        brief="HIPAA compliant telehealth video consulting platform.",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    try:
        # Test download endpoint
        res = client.get(f"/projects/{project.id}/presentation-pdf")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert "attachment; filename=" in res.headers["content-disposition"]
        assert res.content.startswith(b"%PDF-1.")

        # Test preview endpoint
        res_prev = client.get(f"/projects/{project.id}/preview-presentation-pdf")
        assert res_prev.status_code == 200
        assert res_prev.headers["content-type"] == "application/pdf"
        assert "inline; filename=" in res_prev.headers["content-disposition"]
        assert res_prev.content.startswith(b"%PDF-1.")

        # Test 404 for non-existent project
        non_existent_id = uuid4()
        res_404 = client.get(f"/projects/{non_existent_id}/presentation-pdf")
        assert res_404.status_code == 404

    finally:
        db.delete(project)
        db.commit()
