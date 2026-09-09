"""
Unit and Integration Tests for Workspace Cross-Service Topology & Architecture Matrix
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestWorkspaceTopology:
    def test_workspace_topology_graph(self):
        """Creates a workspace with 2 linked microservices and validates topology extraction."""
        # 1. Create Workspace
        ws_res = client.post("/workspaces", json={
            "name": "FinTech Payment & Ledger Mesh",
            "description": "Distributed financial microservices architecture"
        })
        assert ws_res.status_code == 200
        ws_id = ws_res.json()["id"]

        # 2. Create Project 1 (Auth & Account Gateway)
        p1_res = client.post("/projects/", json={
            "name": "Account Gateway Service",
            "brief": "User authentication, JWT tokens, and account profile management with REST API."
        })
        assert p1_res.status_code == 200
        p1_id = p1_res.json()["id"]
        client.post(f"/projects/{p1_id}/generate")

        # 3. Create Project 2 (Ledger & Settlement Service)
        p2_res = client.post("/projects/", json={
            "name": "Ledger Settlement Service",
            "brief": "Double-entry transaction ledger and payment processing with relational schema."
        })
        assert p2_res.status_code == 200
        p2_id = p2_res.json()["id"]
        client.post(f"/projects/{p2_id}/generate")

        # 4. Link projects to workspace
        link1 = client.post(f"/workspaces/{ws_id}/projects/{p1_id}")
        assert link1.status_code == 200
        link2 = client.post(f"/workspaces/{ws_id}/projects/{p2_id}")
        assert link2.status_code == 200

        # 5. Fetch Topology
        top_res = client.get(f"/workspaces/{ws_id}/topology")
        assert top_res.status_code == 200
        top_data = top_res.json()

        assert top_data["workspace_id"] == ws_id
        assert top_data["workspace_name"] == "FinTech Payment & Ledger Mesh"
        assert top_data["nodes_count"] == 2
        assert top_data["edges_count"] == 1
        assert "mesh_health_score" in top_data
        assert top_data["mesh_health_score"] >= 90.0

        # Check node structure
        node1 = next(n for n in top_data["nodes"] if n["id"] == p1_id)
        assert node1["name"] == "Account Gateway Service"
        assert node1["type"] == "gateway"
        assert "status" in node1

        node2 = next(n for n in top_data["nodes"] if n["id"] == p2_id)
        assert node2["name"] == "Ledger Settlement Service"
        assert node2["type"] == "service"

        # Check edge structure
        edge = top_data["edges"][0]
        assert edge["source"] == p1_id
        assert edge["target"] == p2_id
        assert "gRPC / HTTP/2" in edge["protocol"]
        assert "auth_mode" in edge
