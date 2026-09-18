import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.models import Project, ArtifactNode, ArtifactSection
from app.database import get_db
from app.agents.iac_generator import (
    generate_project_iac_bundle,
    generate_all_iac_packages,
    _generate_terraform_aws,
    _generate_terraform_gcp,
    _generate_kubernetes_manifests,
    _generate_env_matrix,
)


def test_iac_generator_direct_functions():
    slug = "test-saas"
    app_name = "Test SaaS API"

    aws_files = _generate_terraform_aws(slug, app_name)
    assert len(aws_files) == 3
    aws_paths = [f.path for f in aws_files]
    assert "terraform/aws/main.tf" in aws_paths
    assert "terraform/aws/variables.tf" in aws_paths
    assert "terraform/aws/outputs.tf" in aws_paths

    # Check AWS content
    main_tf = next(f for f in aws_files if f.path == "terraform/aws/main.tf")
    assert "aws_ecs_cluster" in main_tf.content
    assert "aws_db_instance" in main_tf.content
    assert "aws_security_group" in main_tf.content

    # GCP
    gcp_files = _generate_terraform_gcp(slug, app_name)
    assert len(gcp_files) == 3
    gcp_main = next(f for f in gcp_files if f.path == "terraform/gcp/main.tf")
    assert "google_cloud_run_v2_service" in gcp_main.content
    assert "google_sql_database_instance" in gcp_main.content

    # Kubernetes
    k8s_files = _generate_kubernetes_manifests(slug, app_name)
    assert len(k8s_files) == 5
    k8s_paths = [f.path for f in k8s_files]
    assert "k8s/deployment.yaml" in k8s_paths
    assert "k8s/service.yaml" in k8s_paths
    assert "k8s/ingress.yaml" in k8s_paths
    assert "k8s/hpa.yaml" in k8s_paths
    assert "k8s/configmap.yaml" in k8s_paths

    k8s_deploy = next(f for f in k8s_files if f.path == "k8s/deployment.yaml")
    assert "livenessProbe" in k8s_deploy.content
    assert "readinessProbe" in k8s_deploy.content

    # Env matrix
    env_files = _generate_env_matrix(slug, app_name)
    assert len(env_files) == 3
    assert any("DATABASE_URL" in f.content for f in env_files)


def test_iac_generator_api_endpoints():
    client = TestClient(app)
    db = next(get_db())

    # Create dummy project
    project = Project(
        id=uuid4(),
        name="CloudOps Nexus App",
        brief="Cloud native microservice architecture",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    try:
        # Test full catalog endpoint
        res = client.get(f"/projects/{project.id}/iac")
        assert res.status_code == 200
        catalog = res.json()
        assert catalog["project_id"] == str(project.id)
        assert "aws" in catalog["available_providers"]
        assert "gcp" in catalog["available_providers"]
        assert "kubernetes" in catalog["available_providers"]
        assert "env" in catalog["available_providers"]
        assert len(catalog["packages"]) == 4

        # Test specific provider endpoint: AWS
        res_aws = client.get(f"/projects/{project.id}/iac/aws")
        assert res_aws.status_code == 200
        bundle_aws = res_aws.json()
        assert bundle_aws["provider"] == "aws"
        assert len(bundle_aws["files"]) >= 3
        assert len(bundle_aws["deployment_steps"]) > 0

        # Test specific provider endpoint: Kubernetes
        res_k8s = client.get(f"/projects/{project.id}/iac/kubernetes")
        assert res_k8s.status_code == 200
        bundle_k8s = res_k8s.json()
        assert bundle_k8s["provider"] == "kubernetes"
        assert len(bundle_k8s["files"]) == 5

        # Test generate POST endpoint
        res_gen = client.post(f"/projects/{project.id}/generate-iac")
        assert res_gen.status_code == 200
        assert "packages" in res_gen.json()

    finally:
        db.delete(project)
        db.commit()
