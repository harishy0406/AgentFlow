"""
Unit and Integration Tests for CI/CD Pipeline & GitHub Actions Generator
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestCicdGenerator:
    def test_cicd_pipeline_generation(self):
        """Creates a test project and validates CI/CD, Dockerfile, Compose, and deploy script generation."""
        # 1. Create project
        create_res = client.post("/projects/", json={
            "name": "DevOps Microservice",
            "brief": "A high-performance FastAPI microservice with PostgreSQL and Redis caching for distributed events."
        })
        assert create_res.status_code == 200
        proj_id = create_res.json()["id"]

        # 2. Trigger generation
        gen_res = client.post(f"/projects/{proj_id}/generate")
        assert gen_res.status_code == 200

        # 3. Test GET /projects/{id}/cicd-pipeline
        get_res = client.get(f"/projects/{proj_id}/cicd-pipeline")
        assert get_res.status_code == 200
        pipeline_data = get_res.json()

        assert "files" in pipeline_data
        assert pipeline_data["files_count"] == 4
        file_paths = [f["path"] for f in pipeline_data["files"]]
        assert ".github/workflows/ci.yml" in file_paths
        assert "Dockerfile.prod" in file_paths
        assert "docker-compose.prod.yml" in file_paths
        assert "deploy.sh" in file_paths

        # Verify GitHub Actions CI workflow content
        ci_file = next(f for f in pipeline_data["files"] if f["path"] == ".github/workflows/ci.yml")
        assert "name: CI Pipeline" in ci_file["content"]
        assert "pytest" in ci_file["content"]
        assert "docker/build-push-action" in ci_file["content"]
        assert "runs-on: ubuntu-latest" in ci_file["content"]

        # Verify Dockerfile.prod content
        docker_file = next(f for f in pipeline_data["files"] if f["path"] == "Dockerfile.prod")
        assert "FROM python:3.11-slim AS builder" in docker_file["content"]
        assert "USER appuser" in docker_file["content"]
        assert "HEALTHCHECK" in docker_file["content"]
        assert "uvicorn" in docker_file["content"]

        # Verify docker-compose.prod.yml
        compose_file = next(f for f in pipeline_data["files"] if f["path"] == "docker-compose.prod.yml")
        assert "version: '3.8'" in compose_file["content"]
        assert "api:" in compose_file["content"]
        assert "networks:" in compose_file["content"]

        # Verify deploy.sh
        deploy_file = next(f for f in pipeline_data["files"] if f["path"] == "deploy.sh")
        assert "#!/usr/bin/env bash" in deploy_file["content"]
        assert "docker compose" in deploy_file["content"]
        assert "HEALTH_URL" in deploy_file["content"]

        # 4. Test POST /projects/{id}/generate-cicd
        post_res = client.post(f"/projects/{proj_id}/generate-cicd")
        assert post_res.status_code == 200
        post_data = post_res.json()
        assert post_data["status"] == "success"
        assert post_data["files_count"] == 4
