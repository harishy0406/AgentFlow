"""
Unit & Integration Tests for Project Architectural Velocity & Quality Signal Evaluator
"""

from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.models import Project, ArtifactNode, ArtifactSection
from app.agents.quality_signals import calculate_project_velocity

client = TestClient(app)


def test_calculate_project_velocity_with_missing_artifacts():
    db = next(get_db())
    project = Project(
        id=uuid4(),
        name="Empty Skeleton Project",
        brief="Project without generated artifacts.",
    )
    db.add(project)
    db.commit()

    vel = calculate_project_velocity(project.id, db)
    assert vel["project_id"] == str(project.id)
    assert vel["completion_pct"] == 0.0
    assert vel["overall_quality_score"] == 0.0
    assert "Drafting Required" in vel["rating_badge"]
    assert len(vel["artifact_breakdown"]) == 6
    assert vel["is_scaffold_ready"] is False


def test_calculate_project_velocity_with_populated_artifacts():
    db = next(get_db())
    project = Project(
        id=uuid4(),
        name="High Velocity Distributed Mesh",
        brief="Production grade service mesh with full specifications.",
    )
    db.add(project)
    db.commit()

    # Add 4 fresh nodes: PRD, SDD, DB_SCHEMA, API_SPEC
    node_types = ["PRD", "SDD", "DB_SCHEMA", "API_SPEC"]
    for atype in node_types:
        node = ArtifactNode(
            project_id=project.id,
            artifact_type=atype,
            version=1,
            status="fresh",
            quality_signal_score=0.92,
        )
        db.add(node)
        db.commit()
        db.add(
            ArtifactSection(
                artifact_node_id=node.id,
                section_key="main",
                content=f"FR-01: System shall handle {atype} with high durability and security.",
                content_hash=f"hash_{atype}",
            )
        )
    db.commit()

    # Query endpoint
    res = client.get(f"/projects/{project.id}/velocity")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == str(project.id)
    # 4 out of 6 is 66.7%
    assert 60.0 <= data["completion_pct"] <= 70.0
    assert data["overall_quality_score"] >= 80.0
    assert "A" in data["rating_badge"]
    assert data["total_sections"] == 4
    assert data["total_words"] > 0
    assert data["is_scaffold_ready"] is True
    assert data["complexity_index"] >= 1.0


def test_velocity_404_for_nonexistent_project():
    res = client.get(f"/projects/{uuid4()}/velocity")
    assert res.status_code == 404
