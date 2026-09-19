import json
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.models import Project, ArtifactNode, ArtifactSection
from app.database import get_db
from app.agents.seed_data_generator import generate_project_seed_data


def test_seed_data_generator_direct_logic():
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="Crypto Escrow Hub",
        brief="Decentralized escrow smart contract orchestration with fiat on-ramp.",
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
        content="""CREATE TABLE escrows (
            id UUID PRIMARY KEY,
            contract_code VARCHAR(64) NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            is_released BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL
        );
        CREATE TABLE parties (
            id UUID PRIMARY KEY,
            wallet_address VARCHAR(42) NOT NULL,
            email VARCHAR(128) NOT NULL
        );""",
        content_hash="hash_escrow_seed_123",
    )
    db.add(section)
    db.commit()
    db.refresh(project)

    try:
        catalog = generate_project_seed_data(str(project.id), db, count_per_table=4)

        assert catalog.project_id == project.id
        assert catalog.project_name == project.name
        assert catalog.total_records == 8
        assert len(catalog.entities) == 2

        # Check SQL Output
        assert "BEGIN;" in catalog.sql_script
        assert "INSERT INTO escrows" in catalog.sql_script
        assert "INSERT INTO parties" in catalog.sql_script
        assert "COMMIT;" in catalog.sql_script

        # Check JSON Fixture
        data = json.loads(catalog.json_fixture)
        assert "escrows" in data
        assert "parties" in data
        assert len(data["escrows"]) == 4
        assert len(data["parties"]) == 4
        assert "@example.com" in data["parties"][0]["email"]

        # Check Python Factory
        assert "class EscrowsFactory" in catalog.python_factory_code
        assert "class PartiesFactory" in catalog.python_factory_code
        assert "factory.Faker('email')" in catalog.python_factory_code

        # Check TypeScript Seeder
        assert "prisma.escrows.upsert" in catalog.typescript_seed_code
        assert "prisma.parties.upsert" in catalog.typescript_seed_code
    finally:
        db.delete(project)
        db.commit()


def test_seed_data_api_endpoints():
    client = TestClient(app)
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="Fleet Logistics",
        brief="Real-time freight truck dispatching and cargo load optimization.",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    try:
        # 1. GET /projects/{id}/seed-data
        res = client.get(f"/projects/{project.id}/seed-data?count=3")
        assert res.status_code == 200
        data = res.json()
        assert data["project_name"] == "Fleet Logistics"
        assert data["total_records"] > 0
        assert "sql_script" in data

        # 2. Download SQL script
        res_sql = client.get(f"/projects/{project.id}/seed-data/seed.sql")
        assert res_sql.status_code == 200
        assert "application/sql" in res_sql.headers["content-type"]
        assert "seed.sql" in res_sql.headers["content-disposition"]
        assert "INSERT INTO" in res_sql.text

        # 3. Download JSON fixture
        res_json = client.get(f"/projects/{project.id}/seed-data/seeds.json")
        assert res_json.status_code == 200
        assert "application/json" in res_json.headers["content-type"]
        assert "seeds.json" in res_json.headers["content-disposition"]
        parsed = json.loads(res_json.text)
        assert isinstance(parsed, dict)

        # 4. 404 for invalid project
        random_id = uuid4()
        res_404 = client.get(f"/projects/{random_id}/seed-data")
        assert res_404.status_code == 404
    finally:
        db.delete(project)
        db.commit()
