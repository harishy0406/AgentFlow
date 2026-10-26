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


def test_all_four_suggested_prompts_and_version_diff():
    client = TestClient(app)
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="Four Prompts Comprehensive Platform",
        brief="Testing all 4 AI Chat suggested prompts",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Add all 5 relevant nodes
    nodes = {}
    for atype in ["PRD", "SDD", "DB_SCHEMA", "API_SPEC", "CODE_GENERATION"]:
        node = ArtifactNode(
            project_id=project.id,
            artifact_type=atype,
            version=1,
            status="fresh",
            quality_signal_score=95.0,
        )
        db.add(node)
        nodes[atype] = node
    db.commit()

    sections = {}
    sec_data = {
        "PRD": ("functional_requirements", "## Requirements\n- FR-1 Initial PRD requirement"),
        "SDD": ("architecture_overview", "## System Architecture\nInitial modular monolith"),
        "DB_SCHEMA": ("relational_ddl", "CREATE TABLE users (id UUID PRIMARY KEY, email VARCHAR(255));"),
        "API_SPEC": ("openapi_yaml", "openapi: 3.0.0\ninfo:\n  title: API\npaths:\n  /users:\n    get:\n      summary: Get users"),
        "CODE_GENERATION": ("code_bundle", "### File: app.py\n```python\nprint('app')\n```"),
    }
    for atype, (skey, scontent) in sec_data.items():
        sec = ArtifactSection(
            artifact_node_id=nodes[atype].id,
            section_key=skey,
            content=scontent,
            content_hash=compute_content_hash(scontent),
        )
        db.add(sec)
        sections[atype] = sec
    db.commit()

    try:
        # Prompt 1: DB_SCHEMA - audit_logs
        p1 = {
            "instruction": "Add an audit_logs table to the DB Schema with user_id, action, timestamp",
            "target_artifact": "DB_SCHEMA",
        }
        r1 = client.post(f"/projects/{project.id}/chat-modify", json=p1)
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["target_artifact"] == "DB_SCHEMA"
        assert "audit_logs" in d1["updated_section_content"]
        assert d1["previous_section_content"] == "CREATE TABLE users (id UUID PRIMARY KEY, email VARCHAR(255));"

        # Verify version history snapshot was created and node version incremented
        v1_res = client.get(f"/sections/{sections['DB_SCHEMA'].id}/versions")
        assert v1_res.status_code == 200
        v1_list = v1_res.json()
        assert len(v1_list) >= 1
        assert v1_list[0]["version"] == 1
        assert v1_list[0]["content"] == d1["previous_section_content"]

        # Re-run same prompt: verify it updates cleanly without duplicating table
        r1_repeat = client.post(f"/projects/{project.id}/chat-modify", json=p1)
        assert r1_repeat.status_code == 200
        d1_repeat = r1_repeat.json()
        assert d1_repeat["updated_section_content"].count("CREATE TABLE IF NOT EXISTS audit_logs") == 1

        # Prompt 2: API_SPEC - Google OAuth endpoint
        p2 = {
            "instruction": "Add OAuth Google Login endpoint /api/v1/auth/google to API Spec",
            "target_artifact": "API_SPEC",
        }
        r2 = client.post(f"/projects/{project.id}/chat-modify", json=p2)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["target_artifact"] == "API_SPEC"
        assert "/api/v1/auth/google" in d2["updated_section_content"]
        assert "Google Login" in d2["updated_section_content"] or "OAuth" in d2["updated_section_content"]

        # Prompt 3: PRD - 2FA requirement
        p3 = {
            "instruction": "Add 2FA Two-Factor Authentication requirement to PRD",
            "target_artifact": "PRD",
        }
        r3 = client.post(f"/projects/{project.id}/chat-modify", json=p3)
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["target_artifact"] == "PRD"
        assert "Two-Factor Authentication" in d3["updated_section_content"] or "2FA" in d3["updated_section_content"]

        # Prompt 4: SDD - Redis session caching
        p4 = {
            "instruction": "Update SDD architecture to use Redis session caching",
            "target_artifact": "SDD",
        }
        r4 = client.post(f"/projects/{project.id}/chat-modify", json=p4)
        assert r4.status_code == 200
        d4 = r4.json()
        assert d4["target_artifact"] == "SDD"
        assert "Redis" in d4["updated_section_content"] or "Caching" in d4["updated_section_content"]

    finally:
        from backend.app.models import ArtifactVersion
        for sec in sections.values():
            db.query(ArtifactVersion).filter(ArtifactVersion.section_id == sec.id).delete()
            db.query(ArtifactSection).filter(ArtifactSection.id == sec.id).delete()
        for node in nodes.values():
            db.query(ArtifactNode).filter(ArtifactNode.id == node.id).delete()
        db.query(Project).filter(Project.id == project.id).delete()
        db.commit()


def test_chat_modify_connection_error_resilience(test_project, monkeypatch):
    """
    Verifies that when remote LLM calls raise ConnectionError ('Connection error.')
    during live demos or offline environments, POST /chat-modify does NOT fail with 500
    and instead uses rich deterministic fallbacks across both target and downstream nodes.
    """
    client, project_id = test_project

    # Mock langchain RunnableSequence.invoke to simulate remote API Connection Error
    from langchain_core.runnables import RunnableSequence

    def mock_broken_invoke(self, *args, **kwargs):
        raise ConnectionError("Connection error.")

    monkeypatch.setattr(RunnableSequence, "invoke", mock_broken_invoke)

    # 1. Test PRD modification with connection failure
    payload = {
        "instruction": "Add 2FA Two-Factor Authentication requirement to PRD",
        "target_artifact": "PRD",
    }

    res = client.post(f"/projects/{project_id}/chat-modify", json=payload)
    assert res.status_code == 200, f"Expected 200 but got {res.status_code}: {res.text}"
    data = res.json()
    assert data["status"] == "success"
    assert "Two-Factor Authentication" in data["updated_section_content"] or "2FA" in data["updated_section_content"]
    assert "Explanation" in data["explanation"] or "AI Change Applied" in data["explanation"]
    assert "SDD" in data["regenerated_artifacts"]

    # 2. Test SDD modification with connection failure
    sdd_payload = {
        "instruction": "Update SDD architecture to use Redis session caching",
        "target_artifact": "SDD",
    }
    res2 = client.post(f"/projects/{project_id}/chat-modify", json=sdd_payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert "Redis" in data2["updated_section_content"] or "Caching" in data2["updated_section_content"]

    # 3. Test custom prompt with connection failure
    custom_payload = {
        "instruction": "Add real-time websocket notifications",
        "target_artifact": "PRD",
    }
    res3 = client.post(f"/projects/{project_id}/chat-modify", json=custom_payload)
    assert res3.status_code == 200
    data3 = res3.json()
    assert "websocket notifications" in data3["updated_section_content"].lower()


def test_chat_assistant_qa_offline_fallback(test_project, monkeypatch):
    """
    Verifies that the assistant Q&A endpoint answers the suggested questions
    with rich, coherent responses even when LLM raises connection errors.
    """
    client, project_id = test_project

    # Mock BaseChatModel.invoke to raise connection error
    from langchain_core.language_models.chat_models import BaseChatModel

    def mock_model_fail(self, *args, **kwargs):
        raise ConnectionError("Connection error.")

    monkeypatch.setattr(BaseChatModel, "invoke", mock_model_fail)

    # Test Q&A on DAG architecture
    res1 = client.post(f"/projects/{project_id}/chat", json={"message": "Explain the system architecture and 7-stage DAG flow"})
    assert res1.status_code == 200
    reply1 = res1.json()["reply"]
    assert "DAG Flow" in reply1
    assert "PRD" in reply1
    assert "Selective Regeneration" in reply1

    # Test Q&A on Database Schema
    res2 = client.post(f"/projects/{project_id}/chat", json={"message": "List all database tables, columns, and foreign keys"})
    assert res2.status_code == 200
    reply2 = res2.json()["reply"]
    assert "Database Architecture" in reply2
    assert "users" in reply2

    # Test Q&A on REST API
    res3 = client.post(f"/projects/{project_id}/chat", json={"message": "What are the main REST API endpoints and response codes?"})
    assert res3.status_code == 200
    reply3 = res3.json()["reply"]
    assert "REST API Specifications" in reply3
    assert "200 OK" in reply3
