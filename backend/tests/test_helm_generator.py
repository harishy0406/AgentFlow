"""
Unit & Integration Tests for Kubernetes Helm Chart Generator Engine
"""

import zipfile
import io
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.models import Project
from app.agents.helm_generator import (
    _slugify,
    build_helm_chart_files,
    generate_helm_chart_bundle,
    generate_helm_chart_zip,
)

client = TestClient(app)


class TestHelmGeneratorUnit:
    def test_slugify(self):
        assert _slugify("FinTech UPI 2.0 Engine") == "fintech-upi-20-engine"
        assert _slugify("---special!!chars---") == "specialchars"
        assert _slugify("") == "agentflow-app"

    def test_build_helm_chart_files_structure(self):
        files = build_helm_chart_files(
            app_name="Order Processing Service",
            project_slug="order-processing",
            description="High-availability order processing microservice",
            replica_count=3,
            service_port=8080,
            domain="orders.prod.company.internal",
        )

        assert "order-processing/Chart.yaml" in files
        assert "order-processing/values.yaml" in files
        assert "order-processing/templates/_helpers.tpl" in files
        assert "order-processing/templates/deployment.yaml" in files
        assert "order-processing/templates/service.yaml" in files
        assert "order-processing/templates/ingress.yaml" in files
        assert "order-processing/templates/hpa.yaml" in files
        assert "order-processing/templates/configmap.yaml" in files
        assert "order-processing/templates/secret.yaml" in files
        assert "order-processing/templates/serviceaccount.yaml" in files
        assert "order-processing/templates/NOTES.txt" in files
        assert "order-processing/.helmignore" in files

        # Check values.yaml contents
        values_content = files["order-processing/values.yaml"]
        assert "replicaCount: 3" in values_content
        assert "port: 8080" in values_content
        assert "orders.prod.company.internal" in values_content

        # Check deployment.yaml
        deploy_content = files["order-processing/templates/deployment.yaml"]
        assert "kind: Deployment" in deploy_content
        assert "livenessProbe:" in deploy_content
        assert "readinessProbe:" in deploy_content


class TestHelmGeneratorIntegration:
    def test_helm_chart_json_and_zip_endpoints(self):
        db = next(get_db())
        project = Project(
            id=uuid4(),
            name="Microservice Helm Demo",
            brief="Demonstration microservice for Helm charts",
        )
        db.add(project)
        db.commit()

        # 1. JSON endpoint
        res = client.get(f"/projects/{project.id}/helm-chart?replicas=4&port=9000&format=json")
        assert res.status_code == 200
        data = res.json()
        assert data["project_id"] == str(project.id)
        assert data["chart_name"] == "microservice-helm-demo"
        assert data["file_count"] == 12
        assert "microservice-helm-demo/Chart.yaml" in data["files"]
        assert len(data["deployment_steps"]) >= 4

        # 2. ZIP endpoint
        res_zip = client.get(f"/projects/{project.id}/helm-chart?format=zip")
        assert res_zip.status_code == 200
        assert "application/zip" in res_zip.headers["content-type"]
        assert "microservice-helm-demo-helm-chart.zip" in res_zip.headers["content-disposition"]

        # Validate valid zip archive
        zip_bytes = io.BytesIO(res_zip.content)
        with zipfile.ZipFile(zip_bytes, "r") as zf:
            namelist = zf.namelist()
            assert "microservice-helm-demo/Chart.yaml" in namelist
            assert "microservice-helm-demo/values.yaml" in namelist
            chart_raw = zf.read("microservice-helm-demo/Chart.yaml").decode("utf-8")
            assert "name: microservice-helm-demo" in chart_raw

    def test_helm_chart_404_for_unknown_project(self):
        res = client.get(f"/projects/{uuid4()}/helm-chart")
        assert res.status_code == 404
