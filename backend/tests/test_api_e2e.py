"""
End-to-End API Integration Tests

Tests all core REST API endpoints:
1. Health check (GET /)
2. HITL project clarification (POST /projects/clarify)
3. Project CRUD (POST /projects/, GET /projects, GET /projects/{id})
4. Provider Registry & Model Routing Preview (GET /providers, GET /routing/preview/{artifact_type})
5. Evaluation Runs API (POST /eval/run, GET /eval/runs)
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestHealthAndClarification:
    def test_health_check(self):
        """Root endpoint should return operational status."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "AgentFlow API" in data["message"]

    def test_clarify_project(self):
        """HITL clarify endpoint should return 3-5 clarifying questions for a brief."""
        payload = {
            "brief": "A decentralized peer-to-peer cryptocurrency lending protocol with automated collateral liquidations."
        }
        response = client.post("/projects/clarify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "questions" in data
        assert len(data["questions"]) > 0


class TestProjectLifecycle:
    def test_create_and_read_project(self):
        """Create a new project and retrieve it by ID."""
        payload = {
            "name": "Integration Test Project",
            "brief": "A fast food delivery app with driver dispatching.",
            "clarifications": "Q1: Target audience? A1: Urban commuters."
        }
        create_res = client.post("/projects/", json=payload)
        assert create_res.status_code == 200
        project_data = create_res.json()
        assert project_data["name"] == "Integration Test Project"
        assert project_data["clarifications"] == "Q1: Target audience? A1: Urban commuters."
        assert "id" in project_data

        project_id = project_data["id"]

        # Read back by ID
        get_res = client.get(f"/projects/{project_id}")
        assert get_res.status_code == 200
        fetched = get_res.json()
        assert fetched["id"] == project_id
        assert fetched["name"] == "Integration Test Project"

    def test_list_projects(self):
        """List all projects."""
        res = client.get("/projects")
        assert res.status_code == 200
        projects = res.json()
        assert isinstance(projects, list)

    def test_nonexistent_project_returns_404(self):
        """Requesting an invalid UUID should return 404."""
        res = client.get("/projects/00000000-0000-0000-0000-000000000000")
        assert res.status_code == 404


class TestProviderRegistryAndRouting:
    def test_list_providers(self):
        """Should return available LLM providers (Anthropic, OpenAI, etc.)."""
        res = client.get("/providers")
        assert res.status_code == 200
        providers = res.json()
        assert len(providers) > 0
        names = [p["name"] for p in providers]
        assert "openai" in names or "anthropic" in names

    def test_preview_routing(self):
        """Preview routing decision for PRD artifact."""
        res = client.get("/routing/preview/PRD?context_size=1500")
        assert res.status_code == 200
        decision = res.json()
        assert decision["artifact_type"] == "PRD"
        assert "chosen_provider" in decision
        assert "chosen_model" in decision
        assert "predicted_quality_signal" in decision
        assert "rationale" in decision


class TestEvaluationAPI:
    def test_trigger_and_list_eval_runs(self):
        """Trigger an automated evaluation run and verify it is logged."""
        run_name = "test-ci-eval-batch"
        res = client.post(f"/eval/run?run_name={run_name}&baseline_type=agentflow&limit=2")
        assert res.status_code == 200
        run_data = res.json()
        assert run_data["run_name"] == run_name
        assert run_data["baseline_type"] == "agentflow"
        assert "total_cost_usd" in run_data
        assert "total_latency_ms" in run_data
        assert len(run_data["results"]) == 2

        # Verify listing
        list_res = client.get("/eval/runs")
        assert list_res.status_code == 200
        runs = list_res.json()
        assert any(r["run_name"] == run_name for r in runs)


class TestCodeExportAndPackaging:
    def test_code_files_and_zip_download(self):
        """Create project, generate artifacts, and test code-files + download-zip endpoints."""
        # 1. Create project
        create_res = client.post(
            "/projects/",
            json={
                "name": "Zip Export Test App",
                "brief": "A simple task tracking application with REST endpoints and SQLite database.",
                "clarifications": "1. SQLite\n2. FastAPI",
            },
        )
        assert create_res.status_code == 200
        project_id = create_res.json()["id"]

        # 2. Generate artifacts (runs all 7 nodes including CODE_GENERATION)
        gen_res = client.post(f"/projects/{project_id}/generate")
        assert gen_res.status_code == 200
        artifacts = gen_res.json()
        assert len(artifacts) == 7
        assert any(a["artifact_type"] == "CODE_GENERATION" for a in artifacts)

        # 3. Test GET /projects/{id}/code-files
        code_res = client.get(f"/projects/{project_id}/code-files")
        assert code_res.status_code == 200
        code_data = code_res.json()
        assert code_data["project_name"] == "Zip Export Test App"
        assert code_data["file_count"] >= 1
        assert len(code_data["files"]) >= 1

        # 4. Test GET /projects/{id}/download-zip
        zip_res = client.get(f"/projects/{project_id}/download-zip")
        assert zip_res.status_code == 200
        assert zip_res.headers["content-type"] == "application/zip"
        assert "attachment; filename=" in zip_res.headers["content-disposition"]
        assert len(zip_res.content) > 100  # Non-empty zip file

        # 5. Test PUT /projects/{id}/code-files (direct edit and disk writeback)
        update_res = client.put(
            f"/projects/{project_id}/code-files",
            json={
                "path": "backend/routes.py",
                "content": "# Updated routes\nfrom fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/health')\ndef h(): return {'ok': True}",
            },
        )
        assert update_res.status_code == 200
        up_data = update_res.json()
        assert up_data["status"] == "success"
        assert up_data["path"] == "backend/routes.py"

        # 6. Test GET /projects/{id}/health (real-time scorecard)
        health_res = client.get(f"/projects/{project_id}/health")
        assert health_res.status_code == 200
        health_data = health_res.json()
        assert health_data["project_name"] == "Zip Export Test App"
        assert health_data["overall_readiness_pct"] > 0
        assert health_data["artifact_completion_pct"] == 100.0
        assert health_data["artifacts_generated"] == 7
        assert "readiness_label" in health_data
        assert isinstance(health_data["health_summary"], list)



