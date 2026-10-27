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
    assert len(data["tools"]) == 4

    tool_ids = [t["id"] for t in data["tools"]]
    assert "github" in tool_ids
    assert "jenkins" in tool_ids
    assert "ansible" in tool_ids
    assert "terraform" in tool_ids

    # Check structure
    github_tool = next(t for t in data["tools"] if t["id"] == "github")
    assert github_tool["name"] == "GitHub"
    assert "logs" in github_tool
    assert len(github_tool["logs"]) > 0
    assert "config" in github_tool
    assert "fields" in github_tool

    # 3. POST /projects/{id}/devops-tools/{tool_id}/test
    test_res = client.post(f"/projects/{p_id}/devops-tools/github/test")
    assert test_res.status_code == 200
    test_data = test_res.json()
    assert test_data["status"] == "success"
    assert "github" in test_data["message"].lower()
    assert "latency_ms" in test_data

    # 4. POST /projects/{id}/devops-tools/{tool_id}/trigger
    trigger_res = client.post(f"/projects/{p_id}/devops-tools/jenkins/trigger", json={})
    assert trigger_res.status_code == 200
    trigger_data = trigger_res.json()
    assert trigger_data["status"] == "success"
    assert "jenkins" in trigger_data["message"].lower()
    assert "log" in trigger_data

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
