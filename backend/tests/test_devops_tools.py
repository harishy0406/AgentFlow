import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_devops_tools_endpoints():
    # 1. Create a project
    p_res = client.post("/projects/", json={
        "name": "DevOps Pipeline Test App",
        "brief": "Full CI/CD pipeline automation with GitHub Actions, Jenkins, Ansible, and Terraform."
    })
    assert p_res.status_code == 200
    p_id = p_res.json()["id"]

    # 2. GET /projects/{id}/devops-tools
    tools_res = client.get(f"/projects/{p_id}/devops-tools")
    assert tools_res.status_code == 200
    data = tools_res.json()
    assert "tools" in data
    assert len(data["tools"]) == 6

    tool_ids = [t["id"] for t in data["tools"]]
    assert "github" in tool_ids
    assert "jenkins" in tool_ids
    assert "ansible" in tool_ids
    assert "terraform" in tool_ids
    assert "docker" in tool_ids
    assert "kubernetes" in tool_ids

    # Check structure
    github_tool = next(t for t in data["tools"] if t["id"] == "github")
    assert github_tool["name"] == "GitHub"
    assert "logs" in github_tool
    assert len(github_tool["logs"]) > 0
    assert "config" in github_tool
    assert "fields" in github_tool

    docker_tool = next(t for t in data["tools"] if t["id"] == "docker")
    assert docker_tool["name"] == "Docker Hub"
    assert "scan_on_push" in docker_tool["config"]

    k8s_tool = next(t for t in data["tools"] if t["id"] == "kubernetes")
    assert k8s_tool["name"] == "Kubernetes"
    assert "cluster_endpoint" in k8s_tool["config"]

    # 3. POST /projects/{id}/devops-tools/{tool_id}/test
    test_res = client.post(f"/projects/{p_id}/devops-tools/github/test")
    assert test_res.status_code == 200
    test_data = test_res.json()
    assert test_data["status"] == "success"
    assert "github" in test_data["message"].lower()
    assert "latency_ms" in test_data

    # Test Docker ping
    docker_ping = client.post(f"/projects/{p_id}/devops-tools/docker/test")
    assert docker_ping.status_code == 200
    assert docker_ping.json()["status"] == "success"
    assert "docker" in docker_ping.json()["message"].lower()

    # Test Kubernetes ping
    k8s_ping = client.post(f"/projects/{p_id}/devops-tools/kubernetes/test")
    assert k8s_ping.status_code == 200
    assert k8s_ping.json()["status"] == "success"
    assert "kubernetes" in k8s_ping.json()["message"].lower()

    # 4. POST /projects/{id}/devops-tools/{tool_id}/trigger
    trigger_res = client.post(f"/projects/{p_id}/devops-tools/jenkins/trigger", json={})
    assert trigger_res.status_code == 200
    trigger_data = trigger_res.json()
    assert trigger_data["status"] == "success"
    assert "jenkins" in trigger_data["message"].lower()
    assert "log" in trigger_data

    # Trigger Docker build
    docker_trigger = client.post(f"/projects/{p_id}/devops-tools/docker/trigger", json={})
    assert docker_trigger.status_code == 200
    assert "docker" in docker_trigger.json()["message"].lower()

    # Trigger K8s rollout
    k8s_trigger = client.post(f"/projects/{p_id}/devops-tools/kubernetes/trigger", json={})
    assert k8s_trigger.status_code == 200
    assert "kubernetes" in k8s_trigger.json()["message"].lower()

    # 5. POST /projects/{id}/devops-tools/{tool_id}/configure
    new_config = {
        "repo_url": "https://github.com/custom-org/my-new-repo",
        "branch": "develop",
        "auto_trigger": False
    }
    cfg_res = client.post(f"/projects/{p_id}/devops-tools/github/configure", json=new_config)
    assert cfg_res.status_code == 200
    cfg_data = cfg_res.json()
    assert cfg_data["status"] == "success"
    assert cfg_data["tool"]["config"]["branch"] == "develop"

    # Verify updated tool reflects new configuration
    updated_tools_res = client.get(f"/projects/{p_id}/devops-tools")
    assert updated_tools_res.status_code == 200
    updated_github = next(t for t in updated_tools_res.json()["tools"] if t["id"] == "github")
    assert updated_github["config"]["branch"] == "develop"
