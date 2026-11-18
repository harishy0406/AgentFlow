"""
Unit & Integration Tests for Phase 21: Cloud FinOps & Multi-Cloud Cost Estimator Engine
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.models import Project, ArtifactNode, ArtifactSection
from app.agents.cost_estimator import detect_infrastructure_signals

client = TestClient(app)


class TestInfrastructureSignalDetection:
    def test_detects_fintech_realtime_and_cache_signals(self):
        sdd = "Uses Redis Redlock for distributed locking, Kafka event bus, WebSocket alerts, and PCI-DSS audit logs."
        db_schema = """
        CREATE TABLE IF NOT EXISTS wallets (id UUID PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS ledger_entries (id UUID PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS upi_transactions (id UUID PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS merchants (id UUID PRIMARY KEY);
        """
        api_spec = """
        POST /api/v1/payments/upi
        GET /api/v1/payments/{id}
        POST /api/v1/qr/dynamic
        GET /api/v1/wallets/balance
        POST /api/v1/webhooks/soundbox
        GET /api/v1/health
        """

        signals = detect_infrastructure_signals(sdd, db_schema, api_spec)
        assert signals["tables_count"] == 4
        assert signals["endpoints_count"] == 6
        assert signals["has_cache"] is True
        assert signals["has_queue"] is True
        assert signals["has_realtime"] is True
        assert signals["has_compliance"] is True
        assert signals["has_ai_workload"] is False

    def test_detects_ai_workload_signals(self):
        sdd = "Semantic search powered by pgvector embeddings and OpenAI LLM routing."
        signals = detect_infrastructure_signals(sdd, "", "")
        assert signals["has_ai_workload"] is True
        assert signals["tables_count"] >= 3
        assert signals["endpoints_count"] >= 5


class TestCostEstimatorEndpoint:
    def test_cost_estimate_across_tiers(self):
        db = next(get_db())
        project = Project(
            id=uuid4(),
            name="FinTech UPI Switch",
            brief="High-throughput UPI switch with Redis cache and Kafka settlement queue.",
        )
        db.add(project)
        db.commit()

        sdd_node = ArtifactNode(project_id=project.id, artifact_type="SDD", version=1, status="fresh")
        db_node = ArtifactNode(project_id=project.id, artifact_type="DB_SCHEMA", version=1, status="fresh")
        api_node = ArtifactNode(project_id=project.id, artifact_type="API_SPEC", version=1, status="fresh")
        db.add_all([sdd_node, db_node, api_node])
        db.commit()

        db.add_all([
            ArtifactSection(
                artifact_node_id=sdd_node.id,
                section_key="architecture",
                content="Redis cluster + Kafka event broker + PCI-DSS encryption + LLM fraud scoring.",
                content_hash="h1",
            ),
            ArtifactSection(
                artifact_node_id=db_node.id,
                section_key="tables",
                content="CREATE TABLE users (id INT); CREATE TABLE transactions (id INT); CREATE TABLE ledgers (id INT); CREATE TABLE audit_logs (id INT);",
                content_hash="h2",
            ),
            ArtifactSection(
                artifact_node_id=api_node.id,
                section_key="routes",
                content="GET /api/v1/health\nPOST /api/v1/transfers\nGET /api/v1/transfers/{id}\nGET /api/v1/ledgers",
                content_hash="h3",
            ),
        ])
        db.commit()

        # Startup tier
        r_startup = client.get(f"/projects/{project.id}/cost-estimate?tier=startup")
        assert r_startup.status_code == 200
        d_startup = r_startup.json()
        assert d_startup["tier"] == "startup"
        assert len(d_startup["providers"]) == 3
        assert d_startup["recommended_provider"] in ["AWS", "GCP", "Azure"]
        assert d_startup["detected_signals"]["has_cache"] is True
        assert d_startup["detected_signals"]["has_ai_workload"] is True

        # Growth tier
        r_growth = client.get(f"/projects/{project.id}/cost-estimate?tier=growth")
        assert r_growth.status_code == 200
        d_growth = r_growth.json()
        assert d_growth["lowest_monthly_usd"] > d_startup["lowest_monthly_usd"]

        # Enterprise tier
        r_ent = client.get(f"/projects/{project.id}/cost-estimate?tier=enterprise")
        assert r_ent.status_code == 200
        d_ent = r_ent.json()
        assert d_ent["lowest_monthly_usd"] > d_growth["lowest_monthly_usd"]
        assert len(d_ent["finops_recommendations"]) >= 4

        # Verify reserved savings math for every cloud provider
        for prov in d_ent["providers"]:
            assert prov["annual_reserved_usd"] < prov["annual_on_demand_usd"]
            assert round(prov["annual_on_demand_usd"] - prov["annual_reserved_usd"], 2) == prov["annual_savings_usd"]

    def test_cost_estimate_404_for_unknown_project(self):
        res = client.get(f"/projects/{uuid4()}/cost-estimate")
        assert res.status_code == 404
