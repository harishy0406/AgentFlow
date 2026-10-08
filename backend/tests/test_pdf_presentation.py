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


def test_pdf_presentation_empty_project_with_links():
    """Verify that projects with zero artifact nodes still generate complete 10-slide deck with TOC links."""
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="Empty Initialized App",
        brief="",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    try:
        pdf_bytes = generate_project_presentation_pdf(str(project.id), db)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 5000
        assert pdf_bytes.startswith(b"%PDF-1.")
        # Verify internal link annotations
        assert b"/Link" in pdf_bytes
        assert b"/Annots" in pdf_bytes
    finally:
        db.delete(project)
        db.commit()


def test_pdf_presentation_metadata_endpoint():
    """Verify GET /projects/{id}/presentation-metadata returns 10-slide structural metadata and 404 on invalid ID."""
    client = TestClient(app)
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="FinTech Analytics Deck",
        brief="High-frequency transaction surveillance platform with anomaly detection.",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    try:
        res = client.get(f"/projects/{project.id}/presentation-metadata")
        assert res.status_code == 200
        data = res.json()

        assert data["project_id"] == str(project.id)
        assert data["project_name"] == "FinTech Analytics Deck"
        assert data["total_slides"] == 10
        assert data["format"] == "landscape"
        assert "Executive Dark Midnight" in data["theme"]
        assert data["supported_themes"] == ["dark", "light"]
        assert data["branding"]["brand_name"] == "AgentFlow"
        assert len(data["slides"]) == 10
        assert data["slides"][0]["title"] == "Project Architecture & Executive Brief"
        assert data["slides"][1]["title"] == "Table of Contents & Architectural Agenda"
        assert data["slides"][9]["title"] == "Security Compliance, OWASP Audit & Signoff"
        assert data["download_url"] == f"/projects/{project.id}/presentation-pdf"
        assert data["preview_url"] == f"/projects/{project.id}/preview-presentation-pdf"

        # Verify 404 behavior
        res_404 = client.get(f"/projects/{uuid4()}/presentation-metadata")
        assert res_404.status_code == 404
    finally:
        db.delete(project)
        db.commit()


def test_pdf_presentation_theme_modes_direct():
    """Verify both light and dark theme direct PDF generation produces valid binaries."""
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="OmniCloud Mesh Orchestrator",
        brief="Zero-trust service mesh control plane with eBPF telemetry.",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    try:
        # Dark theme PDF
        dark_pdf = generate_project_presentation_pdf(str(project.id), db, theme="dark")
        assert isinstance(dark_pdf, bytes)
        assert len(dark_pdf) > 5000
        assert dark_pdf.startswith(b"%PDF-1.")
        assert b"/Link" in dark_pdf

        # Light theme PDF
        light_pdf = generate_project_presentation_pdf(str(project.id), db, theme="light")
        assert isinstance(light_pdf, bytes)
        assert len(light_pdf) > 5000
        assert light_pdf.startswith(b"%PDF-1.")
        assert b"/Link" in light_pdf
    finally:
        db.delete(project)
        db.commit()


def test_pdf_presentation_theme_query_params():
    """Verify HTTP endpoints accept ?theme=light and ?theme=dark query parameters."""
    client = TestClient(app)
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="VectorDB Streaming Pipeline",
        brief="Realtime vector embedding ingestion pipeline with hybrid search.",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    try:
        # 1. Download endpoint with ?theme=light
        res_light = client.get(f"/projects/{project.id}/presentation-pdf?theme=light")
        assert res_light.status_code == 200
        assert res_light.headers["content-type"] == "application/pdf"
        assert "_light_presentation.pdf" in res_light.headers["content-disposition"]
        assert res_light.content.startswith(b"%PDF-1.")

        # 2. Preview endpoint with ?theme=dark
        res_dark = client.get(f"/projects/{project.id}/preview-presentation-pdf?theme=dark")
        assert res_dark.status_code == 200
        assert res_dark.headers["content-type"] == "application/pdf"
        assert "inline;" in res_dark.headers["content-disposition"]
        assert res_dark.content.startswith(b"%PDF-1.")

        # 3. Invalid theme should return 422 Unprocessable Entity
        res_invalid = client.get(f"/projects/{project.id}/presentation-pdf?theme=neon_rainbow")
        assert res_invalid.status_code == 422
    finally:
        db.delete(project)
        db.commit()

