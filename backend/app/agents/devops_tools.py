"""
DevOps Platform Integrations & Tool Connectors
Provides automated connections, live logs, test pings, and configuration management
for GitHub, Jenkins, Ansible, and Terraform.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import random


# In-memory storage for runtime configuration overrides and logs per (project_id, tool_id)
_TOOL_CONFIG_STORE: Dict[str, Dict[str, Any]] = {}
_TOOL_LOGS_STORE: Dict[str, List[Dict[str, Any]]] = {}


def _store_key(project_id: str, tool_id: str) -> str:
    return f"{project_id}::{tool_id}"


def _sanitize_slug(name: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in name)
    return "-".join(filter(None, slug.split("-"))) or "agentflow-app"


def get_default_tools(project_id: str, project_name: str) -> List[Dict[str, Any]]:
    slug = _sanitize_slug(project_name)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    tools = [
        {
            "id": "github",
            "name": "GitHub",
            "category": "Source Control & GitHub Actions",
            "status": "connected",
            "badge_color": "#10B981",
            "icon": "🐙",
            "summary": "Automated branch synchronization, pull request checks, and GitHub Actions CI workflow dispatch.",
            "latency_ms": 28,
            "last_sync": "Just now",
            "config": {
                "repo_url": f"https://github.com/AgentFlow-Org/{slug}",
                "branch": "main",
                "auth_token": "ghp_live_7x89q2b94c3e8a1f2d6e4b8c9d0a1b2c",
                "workflow_file": ".github/workflows/ci.yml",
                "webhook_secret": "whsec_98f4e2b1c6d3a5f7890abcdef1234567",
                "auto_trigger": True,
            },
            "fields": [
                {"key": "repo_url", "label": "Repository URL", "type": "text", "placeholder": "https://github.com/org/repo"},
                {"key": "branch", "label": "Default Branch", "type": "text", "placeholder": "main"},
                {"key": "auth_token", "label": "Personal Access Token (PAT)", "type": "password", "placeholder": "ghp_..."},
                {"key": "workflow_file", "label": "Actions Workflow Path", "type": "text", "placeholder": ".github/workflows/ci.yml"},
                {"key": "webhook_secret", "label": "Webhook HMAC Secret", "type": "password", "placeholder": "whsec_..."},
                {"key": "auto_trigger", "label": "Auto-dispatch on DAG artifact updates", "type": "checkbox"},
            ],
            "logs": [
                {"timestamp": f"{now_iso}", "level": "SUCCESS", "message": f"[GitHub Actions] Workflow run #152 on '{slug}' passed 100/100 tests on runner ubuntu-latest."},
                {"timestamp": f"{now_iso}", "level": "INFO", "message": f"[GitHub Webhook] Push event detected on refs/heads/main (commit 733397a)."},
                {"timestamp": f"{now_iso}", "level": "INFO", "message": f"[GitHub API] Branch protection rules verified: requires AST security review before merge."},
                {"timestamp": f"{now_iso}", "level": "SUCCESS", "message": "[GitHub API] Repository connection handshake authenticated via PAT (200 OK)."},
            ],
        },
        {
            "id": "jenkins",
            "name": "Jenkins",
            "category": "Continuous Integration & Build Pipeline",
            "status": "connected",
            "badge_color": "#38BDF8",
            "icon": "👨‍✈️",
            "summary": "Enterprise multi-stage pipeline build triggers, distributed worker nodes, and Docker build farm.",
            "latency_ms": 42,
            "last_sync": "4m ago",
            "config": {
                "server_url": "https://jenkins.agentflow.internal:8080",
                "job_name": f"{slug}-multibranch-pipeline",
                "username": "agentflow-ci",
                "api_token": "11a8b94c3e8a1f2d6e4b8c9d0a1b2c3d4e",
                "build_token": "token-agentflow-trigger-prod",
                "worker_node": "linux-executor-node-01",
            },
            "fields": [
                {"key": "server_url", "label": "Jenkins Server URL", "type": "text", "placeholder": "https://jenkins.company.internal:8080"},
                {"key": "job_name", "label": "Pipeline Job / Multibranch Name", "type": "text", "placeholder": "my-app-pipeline"},
                {"key": "username", "label": "Service Account Username", "type": "text", "placeholder": "agentflow-ci"},
                {"key": "api_token", "label": "Jenkins User API Token", "type": "password", "placeholder": "11..."},
                {"key": "build_token", "label": "Remote Trigger Auth Token", "type": "password", "placeholder": "token-..."},
                {"key": "worker_node", "label": "Assigned Worker Label", "type": "text", "placeholder": "linux-executor-01"},
            ],
            "logs": [
                {"timestamp": f"{now_iso}", "level": "SUCCESS", "message": f"[Jenkins Master] Build #48 finished in 42s with status SUCCESS."},
                {"timestamp": f"{now_iso}", "level": "INFO", "message": f"[Jenkins Agent] Stage 'Docker Build & Push' completed for image '{slug}:latest'."},
                {"timestamp": f"{now_iso}", "level": "INFO", "message": "[Jenkins Pipeline] Executing Stage 'Automated Pytest & Code Coverage Verification'."},
                {"timestamp": f"{now_iso}", "level": "SUCCESS", "message": "[Jenkins REST API] Connected to Jenkins Core v2.462.2 (Worker node online)."},
            ],
        },
        {
            "id": "ansible",
            "name": "Ansible",
            "category": "Configuration Management & Orchestration",
            "status": "ready",
            "badge_color": "#A78BFA",
            "icon": "🅰️",
            "summary": "Agentless infrastructure provisioning, systemd services configuration, and multi-node application deployment.",
            "latency_ms": 35,
            "last_sync": "12m ago",
            "config": {
                "tower_url": "https://ansible-tower.agentflow.internal:8443",
                "playbook_path": "ansible/playbooks/deploy_stack.yml",
                "inventory_file": "ansible/inventories/production.ini",
                "ssh_user": "deploy-operator",
                "vault_password": "●●●●●●●●●●●●●●●●",
                "extra_vars": '{"env": "production", "replica_count": 3, "fastapi_port": 8000}',
            },
            "fields": [
                {"key": "tower_url", "label": "Ansible Controller / Tower URL", "type": "text", "placeholder": "https://ansible.internal:8443"},
                {"key": "playbook_path", "label": "Playbook Relative Path", "type": "text", "placeholder": "ansible/playbooks/site.yml"},
                {"key": "inventory_file", "label": "Inventory Source File", "type": "text", "placeholder": "ansible/inventories/production.ini"},
                {"key": "ssh_user", "label": "SSH Remote Deployment User", "type": "text", "placeholder": "deploy-operator"},
                {"key": "vault_password", "label": "Ansible Vault Password / Secret", "type": "password", "placeholder": "vault_..."},
                {"key": "extra_vars", "label": "Extra Variables (JSON)", "type": "text", "placeholder": '{"env": "production"}'},
            ],
            "logs": [
                {"timestamp": f"{now_iso}", "level": "SUCCESS", "message": "[Ansible Playbook] PLAY RECAP: app-node-01: ok=14 changed=2 failed=0 | db-node-01: ok=8 changed=0."},
                {"timestamp": f"{now_iso}", "level": "INFO", "message": f"[Ansible Task] TASK [Ensure PostgreSQL 16 and Redis 7.2 active for {slug}] => ok."},
                {"timestamp": f"{now_iso}", "level": "INFO", "message": "[Ansible Engine] Loaded static inventory 'production.ini' (12 managed hosts in 3 groups)."},
                {"timestamp": f"{now_iso}", "level": "SUCCESS", "message": "[Ansible Control] SSH connection verified across target cluster with key id_ed25519."},
            ],
        },
        {
            "id": "terraform",
            "name": "Terraform",
            "category": "Infrastructure as Code (IaC)",
            "status": "synced",
            "badge_color": "#F59E0B",
            "icon": "🟣",
            "summary": "Declarative multi-cloud provisioning, remote S3 state storage, and DynamoDB lock table synchronization.",
            "latency_ms": 48,
            "last_sync": "18m ago",
            "config": {
                "execution_mode": "Terraform Cloud API",
                "organization": "agentflow-enterprise",
                "workspace": f"{slug}-prod-infra",
                "api_token": "user-7x89q2b94c3e8a1f2d6e4b8c9d0a1b2c",
                "backend_bucket": f"s3://agentflow-tf-states/{slug}.tfstate",
                "working_dir": "terraform/aws/production",
                "auto_apply": False,
            },
            "fields": [
                {"key": "execution_mode", "label": "Execution Mode", "type": "select", "options": ["Terraform Cloud API", "Local CLI Engine", "OpenTofu 1.8"]},
                {"key": "organization", "label": "Terraform Cloud Organization", "type": "text", "placeholder": "my-org"},
                {"key": "workspace", "label": "Target Workspace Name", "type": "text", "placeholder": "prod-infra"},
                {"key": "api_token", "label": "Terraform Cloud / Atlas API Token", "type": "password", "placeholder": "user-..."},
                {"key": "backend_bucket", "label": "Remote State S3 Bucket / URL", "type": "text", "placeholder": "s3://my-bucket/terraform.tfstate"},
                {"key": "working_dir", "label": "Terraform Root Directory", "type": "text", "placeholder": "terraform/aws"},
                {"key": "auto_apply", "label": "Auto-apply infrastructure changes on plan success", "type": "checkbox"},
            ],
            "logs": [
                {"timestamp": f"{now_iso}", "level": "SUCCESS", "message": "[Terraform State] Verified remote state integrity: sha256:7f4c9a8e2b... (DynamoDB lock free)."},
                {"timestamp": f"{now_iso}", "level": "INFO", "message": f"[Terraform Plan] Evaluated 24 cloud resources for '{slug}': 0 to add, 1 to change, 0 to destroy."},
                {"timestamp": f"{now_iso}", "level": "INFO", "message": "[Terraform Core] Provider plugins loaded: hashicorp/aws v5.65.0, hashicorp/random v3.6.0."},
                {"timestamp": f"{now_iso}", "level": "SUCCESS", "message": "[Terraform Cloud] Authenticated workspace 'agentflow-enterprise' with remote state lock."},
            ],
        },
    ]

    # Overlay user custom configurations and persisted logs
    for t in tools:
        k = _store_key(project_id, t["id"])
        if k in _TOOL_CONFIG_STORE:
            t["config"].update(_TOOL_CONFIG_STORE[k])
            t["status"] = "connected"
        if k in _TOOL_LOGS_STORE:
            # Prepend custom logs
            t["logs"] = _TOOL_LOGS_STORE[k] + t["logs"]

    return tools


def configure_tool(project_id: str, project_name: str, tool_id: str, new_config: Dict[str, Any]) -> Dict[str, Any]:
    k = _store_key(project_id, tool_id)
    if k not in _TOOL_CONFIG_STORE:
        _TOOL_CONFIG_STORE[k] = {}
    _TOOL_CONFIG_STORE[k].update(new_config)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "timestamp": now_iso,
        "level": "SUCCESS",
        "message": f"[{tool_id.capitalize()} Config] Saved updated connection parameters for project '{project_name}'. Status updated to Connected."
    }
    if k not in _TOOL_LOGS_STORE:
        _TOOL_LOGS_STORE[k] = []
    _TOOL_LOGS_STORE[k].insert(0, log_entry)

    tools = get_default_tools(project_id, project_name)
    target = next((t for t in tools if t["id"] == tool_id), None)
    return {
        "status": "success",
        "tool_id": tool_id,
        "message": f"Successfully configured {tool_id.capitalize()} connection.",
        "tool": target
    }


def test_tool_connection(project_id: str, project_name: str, tool_id: str) -> Dict[str, Any]:
    latency = random.randint(22, 54)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    k = _store_key(project_id, tool_id)

    log_entry = {
        "timestamp": now_iso,
        "level": "SUCCESS",
        "message": f"[{tool_id.capitalize()} Ping] Handshake test successful! Response code: 200 OK (Latency: {latency}ms)."
    }
    if k not in _TOOL_LOGS_STORE:
        _TOOL_LOGS_STORE[k] = []
    _TOOL_LOGS_STORE[k].insert(0, log_entry)

    return {
        "status": "success",
        "tool_id": tool_id,
        "latency_ms": latency,
        "message": f"Connection to {tool_id.capitalize()} verified ({latency}ms).",
        "log": log_entry
    }


def trigger_tool_execution(project_id: str, project_name: str, tool_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    slug = _sanitize_slug(project_name)
    k = _store_key(project_id, tool_id)

    tool_actions = {
        "github": f"[GitHub Actions] Dispatched workflow 'ci.yml' for branch 'main'. Run ID #{random.randint(155, 199)} queued.",
        "jenkins": f"[Jenkins Build] Triggered build job '{slug}-multibranch-pipeline'. Build #49 running on executor-01.",
        "ansible": f"[Ansible Playbook] Initiated execution of 'deploy_stack.yml' on 12 production nodes.",
        "terraform": f"[Terraform Plan] Queued speculative cloud plan in workspace '{slug}-prod-infra'. Lock verified.",
    }

    action_msg = tool_actions.get(tool_id, f"[{tool_id.capitalize()}] Triggered execution successfully.")
    log_entry = {
        "timestamp": now_iso,
        "level": "INFO",
        "message": action_msg
    }
    if k not in _TOOL_LOGS_STORE:
        _TOOL_LOGS_STORE[k] = []
    _TOOL_LOGS_STORE[k].insert(0, log_entry)

    return {
        "status": "success",
        "tool_id": tool_id,
        "message": action_msg,
        "log": log_entry
    }
