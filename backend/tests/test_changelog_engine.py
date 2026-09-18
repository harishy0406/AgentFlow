import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agents.changelog_engine import (
    compare_api_specs,
    calculate_semver_bump,
    generate_keep_a_changelog_markdown,
)

client = TestClient(app)


def test_changelog_comparator_and_semver():
    old_spec = """
    GET /api/v1/users - List users
    POST /api/v1/users - Create user
    GET /api/v1/users/{id} - Get user by ID
    DELETE /api/v1/users/{id} - Delete user
    """

    new_spec_breaking = """
    GET /api/v1/users - List users
    POST /api/v1/users - Create user
    # /api/v1/users/{id} was removed!
    """
    changes = compare_api_specs(old_spec, new_spec_breaking)
    breaking = [c for c in changes if c["category"] == "BREAKING"]
    assert len(breaking) >= 1
    assert any("removed" in b["description"].lower() for b in breaking)

    # Major bump test
    semver_major = calculate_semver_bump("v1.2.0", changes)
    assert semver_major["bump_type"] == "MAJOR"
    assert semver_major["suggested_version"] == "v2.0.0"

    # Non-breaking additions test
    new_spec_adds = """
    GET /api/v1/users - List users
    POST /api/v1/users - Create user
    GET /api/v1/users/{id} - Get user by ID
    DELETE /api/v1/users/{id} - Delete user
    GET /api/v1/users/{id}/orders - List user orders
    """
    changes_add = compare_api_specs(old_spec, new_spec_adds)
    adds = [c for c in changes_add if c["category"] == "NON_BREAKING_ADD"]
    assert len(adds) == 1
    assert adds[0]["endpoint"] == "/api/v1/users/{id}/orders"

    semver_minor = calculate_semver_bump("v1.2.0", changes_add)
    assert semver_minor["bump_type"] == "MINOR"
    assert semver_minor["suggested_version"] == "v1.3.0"

    # Markdown rendering test
    md = generate_keep_a_changelog_markdown("User API", semver_major, changes)
    assert "# Changelog — User API" in md
    assert "### 🚨 Breaking Changes" in md


def test_changelog_api_endpoints():
    # 1. Create and scaffold test project
    p_res = client.post("/projects/", json={
        "name": "E-Commerce Catalog Service",
        "brief": "Microservice for managing product catalogs, categories, and inventory."
    })
    assert p_res.status_code == 200
    p_id = p_res.json()["id"]

    client.post(f"/projects/{p_id}/generate")

    # 2. Get active changelog
    cl_res = client.get(f"/projects/{p_id}/changelog")
    assert cl_res.status_code == 200
    report = cl_res.json()

    assert report["project_id"] == p_id
    assert "semver" in report
    assert report["semver"]["bump_type"] in ["MAJOR", "MINOR", "PATCH"]
    assert "markdown_changelog" in report
    assert len(report["markdown_changelog"]) > 0

    # 3. Detect breaking changes against an altered spec
    breaking_spec = """
    GET /api/v1/catalog/health - Health check
    # All products endpoints deleted
    """
    detect_res = client.post(f"/projects/{p_id}/detect-breaking-changes", json={
        "updated_api_spec": breaking_spec
    })
    assert detect_res.status_code == 200
    detect_report = detect_res.json()
    assert detect_report["semver"]["bump_type"] == "MAJOR"
    assert detect_report["breaking_changes_count"] > 0
