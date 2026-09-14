import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agents.sdk_generator import (
    _to_pascal_case,
    _to_camel_case,
    _generate_method_name,
    _generate_typescript_sdk,
    _generate_python_sdk,
    _generate_curl_cheat_sheet,
)

client = TestClient(app)


def test_sdk_generator_naming_helpers():
    assert _to_pascal_case("user_profile") == "UserProfile"
    assert _to_pascal_case("e-commerce-api") == "ECommerceApi"
    assert _to_camel_case("user_profile") == "userProfile"

    assert _generate_method_name("GET", "/api/v1/users") == "listUsers"
    assert _generate_method_name("GET", "/api/v1/users/{id}") == "getUsers"
    assert _generate_method_name("POST", "/api/v1/orders") == "createOrders"
    assert _generate_method_name("DELETE", "/api/v1/orders/{id}") == "deleteOrders"


def test_sdk_generator_templates():
    routes = [
        {"method": "GET", "path": "/api/v1/projects", "summary": "List all projects"},
        {"method": "POST", "path": "/api/v1/projects", "summary": "Create project"},
    ]
    schemas = {
        "Project": {
            "id": "uuid",
            "name": "str",
            "created_at": "datetime"
        }
    }

    # TypeScript SDK test
    ts_files = _generate_typescript_sdk("my-api", routes, schemas)
    ts_paths = [f["path"] for f in ts_files]
    assert "src/client.ts" in ts_paths
    assert "src/types.ts" in ts_paths
    assert "package.json" in ts_paths
    assert "README.md" in ts_paths

    types_file = next(f for f in ts_files if f["path"] == "src/types.ts")
    assert "export interface Project" in types_file["content"]

    client_file = next(f for f in ts_files if f["path"] == "src/client.ts")
    assert "class ApiClient" in client_file["content"]
    assert "async listProjects(" in client_file["content"]

    # Python SDK test
    py_files = _generate_python_sdk("my-api", routes, schemas)
    py_paths = [f["path"] for f in py_files]
    assert "my_api/client.py" in py_paths
    assert "my_api/models.py" in py_paths
    assert "pyproject.toml" in py_paths
    assert "README.md" in py_paths

    models_file = next(f for f in py_files if f["path"] == "my_api/models.py")
    assert "class Project(BaseModel):" in models_file["content"]

    py_client = next(f for f in py_files if f["path"] == "my_api/client.py")
    assert "class ApiClient:" in py_client["content"]
    assert "def list_projects(" in py_client["content"]

    # cURL cheat sheet test
    curl_files = _generate_curl_cheat_sheet("my-api", routes)
    curl_paths = [f["path"] for f in curl_files]
    assert "curl_recipes.sh" in curl_paths
    assert "endpoints.http" in curl_paths


def test_sdk_api_endpoints():
    # 1. Create and scaffold a test project
    p_res = client.post("/projects/", json={
        "name": "Cloud Logistics API",
        "brief": "Warehouse logistics and freight dispatch platform."
    })
    assert p_res.status_code == 200
    p_id = p_res.json()["id"]

    client.post(f"/projects/{p_id}/generate")

    # 2. Get full SDK catalog
    cat_res = client.get(f"/projects/{p_id}/sdk")
    assert cat_res.status_code == 200
    catalog = cat_res.json()
    assert catalog["project_id"] == p_id
    assert "typescript" in catalog["available_languages"]
    assert "python" in catalog["available_languages"]
    assert "curl" in catalog["available_languages"]

    # Verify TypeScript package bundle
    ts_pkg = catalog["packages"]["typescript"]
    assert ts_pkg["language"] == "typescript"
    assert len(ts_pkg["files"]) >= 4
    assert any(f["path"] == "src/client.ts" for f in ts_pkg["files"])

    # 3. Get single language bundle
    py_res = client.get(f"/projects/{p_id}/sdk/python")
    assert py_res.status_code == 200
    py_bundle = py_res.json()
    assert py_bundle["language"] == "python"
    assert "pip install" in py_bundle["install_command"]
    assert len(py_bundle["files"]) >= 4

    # 4. Trigger regenerate endpoint
    gen_res = client.post(f"/projects/{p_id}/generate-sdk")
    assert gen_res.status_code == 200
    gen_cat = gen_res.json()
    assert "curl" in gen_cat["packages"]
