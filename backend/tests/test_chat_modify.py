import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import get_db
from backend.app.models import Project, ArtifactNode, ArtifactSection
from backend.app.agents.graph_engine import TOPOLOGICAL_ORDER, compute_content_hash


@pytest.fixture
def test_project():
    client = TestClient(app)
    db = next(get_db())

    # Create dummy project
    project = Project(
        id=uuid4(),
        name="Test Chat Modify Platform",
        brief="A platform to test chat-to-modify workflow",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Add PRD and SDD artifact nodes
    prd_node = ArtifactNode(
        project_id=project.id,
        artifact_type="PRD",
        version=1,
        status="fresh",
        quality_signal_score=95.0,
    )
    sdd_node = ArtifactNode(
        project_id=project.id,
        artifact_type="SDD",
        version=1,
        status="fresh",
        quality_signal_score=94.0,
    )
    cg_node = ArtifactNode(
        project_id=project.id,
        artifact_type="CODE_GENERATION",
        version=1,
        status="fresh",
        quality_signal_score=93.0,
    )
    db.add_all([prd_node, sdd_node, cg_node])
    db.commit()

    prd_sec = ArtifactSection(
        artifact_node_id=prd_node.id,
        section_key="functional_requirements",
        content="## Requirements\n- FR-1 Initial test requirement",
        content_hash=compute_content_hash("## Requirements\n- FR-1 Initial test requirement"),
    )
    sdd_sec = ArtifactSection(
        artifact_node_id=sdd_node.id,
        section_key="architecture_overview",
        content="## Architecture\nOverview details",
        content_hash=compute_content_hash("## Architecture\nOverview details"),
    )
    cg_sec = ArtifactSection(
        artifact_node_id=cg_node.id,
        section_key="code_bundle",
        content="### File: backend/main.py\n```python\nprint('hello')\n```",
        content_hash=compute_content_hash("### File: backend/main.py\n```python\nprint('hello')\n```"),
    )
    db.add_all([prd_sec, sdd_sec, cg_sec])
    db.commit()

    from backend.app.models import section_traces
    db.execute(
        section_traces.insert().values(
            upstream_section_id=prd_sec.id,
            downstream_section_id=sdd_sec.id,
        )
    )
    db.commit()

    yield client, project.id

    # Cleanup
    db.query(ArtifactSection).filter(ArtifactSection.artifact_node_id.in_([prd_node.id, sdd_node.id, cg_node.id])).delete()
    db.query(ArtifactNode).filter(ArtifactNode.project_id == project.id).delete()
    db.query(Project).filter(Project.id == project.id).delete()
    db.commit()


def test_chat_modify_prd_flow(test_project):
    client, project_id = test_project

    payload = {
        "instruction": "Add OAuth2 Google and GitHub Single Sign-On and multi-factor authentication",
        "target_artifact": "PRD",
        "target_section_key": "functional_requirements"
    }

    res = client.post(f"/projects/{project_id}/chat-modify", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["project_id"] == str(project_id)
    assert data["target_artifact"] == "PRD"
    assert data["target_section_key"] == "functional_requirements"
    assert "cascaded_downstream_artifacts" in data
    assert "SDD" in data["cascaded_downstream_artifacts"]
    assert "message" in data
    assert "OAuth2" in data["message"] or "OAuth2" in data["updated_section_content"]


def test_chat_modify_auto_target(test_project):
    client, project_id = test_project

    payload = {
        "instruction": "Migrate database schema to PostgreSQL 16 with UUID primary keys and add indexes",
        "target_artifact": "AUTO"
    }

    res = client.post(f"/projects/{project_id}/chat-modify", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["project_id"] == str(project_id)
    assert data["target_artifact"] in ["DB_SCHEMA", "SDD", "PRD"]
    assert isinstance(data["cascaded_downstream_artifacts"], list)
