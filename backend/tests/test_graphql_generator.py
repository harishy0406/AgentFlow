import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.models import Project, ArtifactNode, ArtifactSection
from app.database import get_db
from app.agents.graphql_generator import generate_project_graphql


def test_graphql_generator_direct_logic():
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="FinTech Ledger",
        brief="Double-entry financial ledger and multi-currency balance tracking service.",
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
        content="""CREATE TABLE accounts (
            id UUID PRIMARY KEY,
            account_number VARCHAR(64) NOT NULL,
            currency VARCHAR(3) NOT NULL,
            balance NUMERIC(14, 2) NOT NULL,
            is_frozen BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL
        );
        CREATE TABLE entries (
            id UUID PRIMARY KEY,
            account_id UUID NOT NULL,
            amount NUMERIC(14, 2) NOT NULL,
            description TEXT
        );""",
        content_hash="hash_fintech_123",
    )
    db.add(section)
    db.commit()
    db.refresh(project)

    try:
        gql = generate_project_graphql(str(project.id), db)

        assert gql.project_id == project.id
        assert gql.project_name == project.name
        assert len(gql.types) == 2

        # Verify SDL
        assert "type Account {" in gql.schema_sdl
        assert "type Entry {" in gql.schema_sdl
        assert "type Query {" in gql.schema_sdl
        assert "type Mutation {" in gql.schema_sdl
        assert "getAccount(id: ID!): Account" in gql.schema_sdl
        assert "createAccount(input: CreateAccountInput!): Account!" in gql.schema_sdl

        # Verify Code Stubs
        assert "@strawberry.type" in gql.resolver_code_python
        assert "class Account:" in gql.resolver_code_python
        assert "export const resolvers =" in gql.resolver_code_typescript
        assert "listAccounts" in gql.query_examples
    finally:
        db.delete(project)
        db.commit()


def test_graphql_api_endpoints():
    client = TestClient(app)
    db = next(get_db())

    project = Project(
        id=uuid4(),
        name="E-Commerce Storefront",
        brief="Multi-tenant marketplace catalog and inventory manager.",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    try:
        # 1. GET /projects/{id}/graphql
        res = client.get(f"/projects/{project.id}/graphql")
        assert res.status_code == 200
        data = res.json()
        assert data["project_name"] == "E-Commerce Storefront"
        assert "type Query" in data["schema_sdl"]
        assert data["queries_count"] > 0
        assert data["mutations_count"] > 0

        # 2. GET /projects/{id}/graphql/schema.graphql
        res_sdl = client.get(f"/projects/{project.id}/graphql/schema.graphql")
        assert res_sdl.status_code == 200
        assert "text/plain" in res_sdl.headers["content-type"]
        assert "attachment; filename=" in res_sdl.headers["content-disposition"]
        assert "type Query {" in res_sdl.text

        # 3. 404 for invalid project
        non_existent_id = uuid4()
        res_404 = client.get(f"/projects/{non_existent_id}/graphql")
        assert res_404.status_code == 404
    finally:
        db.delete(project)
        db.commit()
