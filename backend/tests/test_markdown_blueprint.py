import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.models import Project, ArtifactNode, ArtifactSection
from app.database import get_db
from app.reports.markdown_blueprint import generate_project_blueprint_markdown

client = TestClient(app)


def test_markdown_blueprint_direct_generation():
    db = next(get_db())

    # Create test project with artifacts
    project = Project(
        id=uuid4(),
        name="Distributed Event Mesh",
        brief="High-throughput distributed event broker platform with schema validation and consumer group rebalancing.",
    )
    db.add(project)

    # Add DB_SCHEMA artifact
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
        content="""CREATE TABLE topics (
            id UUID PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            partitions INT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE consumers (
            id UUID PRIMARY KEY,
            topic_id UUID REFERENCES topics(id),
            group_id VARCHAR(64) NOT NULL,
            last_offset BIGINT DEFAULT 0
        );""",
        content_hash="hash_mesh_db",
    )
    db.add(section_db)

    # Add API_SPEC artifact
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
        section_key="api_spec_markdown",
        content="""| Method | Path | Description |
|:---|:---|:---|
| GET | /topics | List all registered event topics |
| POST | /topics | Create a new partitioned topic |
| POST | /topics/{id}/publish | Publish binary message event payload |""",
        content_hash="hash_mesh_api",
    )
    db.add(section_api)

    # Add CODE_GENERATION artifact
    node_code = ArtifactNode(
        id=uuid4(),
        project_id=project.id,
        artifact_type="CODE_GENERATION",
        version=1,
        status="fresh",
    )
    db.add(node_code)

    section_code = ArtifactSection(
        id=uuid4(),
        artifact_node_id=node_code.id,
        section_key="code_bundle",
        content="""### File: app/broker.py
```python
def publish_message(topic, message):
    return True
```
### File: app/consumer.py
```python
def consume_events():
    return []
```""",
        content_hash="hash_mesh_code",
    )
    db.add(section_code)
    db.commit()

    # Generate Markdown
    md_content = generate_project_blueprint_markdown(str(project.id), db)
    assert isinstance(md_content, str)
    assert len(md_content) > 500

    # Assert key sections are generated
    assert "# 🏗️ Architecture Blueprint: Distributed Event Mesh" in md_content
    assert "## 📋 Project Metadata" in md_content
    assert "## 1. Executive Mission & System Goals" in md_content
    assert "## 2. System Architecture & Topology" in md_content
    assert "## 3. Relational Database Schema & Models" in md_content
    assert "## 4. REST API Endpoints & Service Contracts" in md_content
    assert "## 5. Repository Topology & Source File Tree" in md_content
    assert "## 6. OWASP Security Shield & Compliance" in md_content
    assert "## 7. Implementation Roadmap & Sprint Backlog" in md_content
    assert "## 8. Local Deployment & Runbook" in md_content

    # Assert extracted entities
    assert "`topics`" in md_content
    assert "`consumers`" in md_content
    assert "/topics" in md_content
    assert "app/broker.py" in md_content
    assert "app/consumer.py" in md_content


def test_markdown_blueprint_fallback_template():
    db = next(get_db())

    # Create project without explicit artifact nodes (triggers template fallback)
    project = Project(
        id=uuid4(),
        name="Crypto Vault Custody",
        brief="Multi-signature institutional digital asset custody and cold storage signing platform.",
    )
    db.add(project)
    db.commit()

    md_content = generate_project_blueprint_markdown(str(project.id), db)
    assert "# 🏗️ Architecture Blueprint: Crypto Vault Custody" in md_content
    assert "Crypto Vault Custody" in md_content
    assert len(md_content) > 300


def test_markdown_blueprint_endpoints():
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="Cloud Native Telemetry",
        brief="Distributed tracing, metrics aggregation, and anomaly detection gateway.",
    )
    db.add(project)
    db.commit()

    # 1. Test metadata JSON endpoint
    res_json = client.get(f"/projects/{project.id}/blueprint-markdown")
    assert res_json.status_code == 200
    data = res_json.json()

    assert data["project_id"] == str(project.id)
    assert data["project_name"] == "Cloud Native Telemetry"
    assert data["project_slug"] == "cloud_native_telemetry"
    assert "markdown_content" in data
    assert data["character_count"] > 200
    assert data["line_count"] > 10
    assert data["sections_count"] >= 5
    assert data["download_url"] == f"/projects/{project.id}/download-blueprint-markdown"

    # 2. Test file download attachment endpoint
    res_file = client.get(f"/projects/{project.id}/download-blueprint-markdown")
    assert res_file.status_code == 200
    assert "text/markdown" in res_file.headers.get("content-type", "")
    assert 'attachment; filename="cloud_native_telemetry_ARCHITECTURE.md"' in res_file.headers.get("content-disposition", "")
    assert res_file.text == data["markdown_content"]


def test_markdown_blueprint_not_found():
    non_existent_id = uuid4()
    res = client.get(f"/projects/{non_existent_id}/blueprint-markdown")
    assert res.status_code == 404

    res_dl = client.get(f"/projects/{non_existent_id}/download-blueprint-markdown")
    assert res_dl.status_code == 404
