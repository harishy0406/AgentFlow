"""
Phase 8+: Dynamic Mock API Sandbox Engine

Provides real-time interactive execution of HTTP requests against generated OpenAPI
and API_SPEC specifications, dynamically synthesizing structured JSON responses,
latency simulation, and HTTP header negotiation without requiring live backend deployment.
"""

import re
import time
import uuid
from uuid import UUID
from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session

from ..models import Project, ArtifactNode
from .openapi_generator import _extract_routes, _extract_schemas


def _match_route_pattern(route_path: str, request_path: str) -> bool:
    """
    Checks if a concrete request path (e.g., /api/v1/users/42)
    matches a parameterized route template (e.g., /api/v1/users/{id}).
    """
    # Normalize leading/trailing slashes
    r_path = "/" + route_path.strip("/")
    req_path = "/" + request_path.strip("/")

    if r_path == req_path:
        return True

    # Replace {param} with regex pattern ([^/]+)
    regex_pattern = re.sub(r"\{[a-zA-Z0-9_]+\}", r"([^/]+)", r_path)
    regex_pattern = f"^{regex_pattern}$"

    return bool(re.match(regex_pattern, req_path))


def _synthesize_mock_response(
    method: str,
    path: str,
    schemas: Dict[str, Any],
    body: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Synthesizes rich, structured mock JSON response based on HTTP method, path, and schemas.
    """
    clean_path = path.strip("/").split("/")
    resource_name = "resource"
    if clean_path:
        last_seg = clean_path[-1]
        is_id_segment = last_seg.startswith("{") or last_seg.isdigit() or len(last_seg) == 36
        if is_id_segment and len(clean_path) > 1:
            resource_name = clean_path[-2]
        else:
            resource_name = last_seg

    # Extract properties from schema (supports OpenAPI format or flat dict)
    schema_properties = {}
    res_norm = resource_name.lower().rstrip("s")
    for schema_name, schema_def in schemas.items():
        s_norm = schema_name.lower().rstrip("s")
        if s_norm in res_norm or res_norm in s_norm or res_norm == "":
            if isinstance(schema_def, dict) and "properties" in schema_def and isinstance(schema_def["properties"], dict):
                for p_k, p_v in schema_def["properties"].items():
                    schema_properties[p_k] = p_v.get("type", "string") if isinstance(p_v, dict) else str(p_v)
            elif isinstance(schema_def, dict):
                for p_k, p_v in schema_def.items():
                    schema_properties[p_k] = p_v if isinstance(p_v, str) else "string"
            break

    def _generate_mock_props(prop_dict: Dict[str, str], idx: int = 1) -> Dict[str, Any]:
        result = {}
        for prop, prop_type in prop_dict.items():
            pt = str(prop_type).lower()
            if "int" in pt:
                result[prop] = idx * 10 if prop != "id" else idx
            elif "bool" in pt:
                result[prop] = True
            elif "float" in pt or "number" in pt or "numeric" in pt:
                result[prop] = round(idx * 19.99, 2)
            elif "uuid" in pt:
                result[prop] = str(uuid.uuid4())
            elif "date" in pt or "time" in pt:
                result[prop] = f"2026-09-0{min(idx, 9)}T12:00:00Z"
            else:
                result[prop] = f"{prop}_{idx}"
        return result

    # 1. DELETE
    if method == "DELETE":
        return {
            "status": "success",
            "message": f"Successfully deleted {resource_name} record.",
            "deleted_id": str(uuid.uuid4())[:8],
            "timestamp": "2026-09-13T21:45:00Z"
        }

    # 2. POST (Create)
    if method == "POST":
        response_item: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "created_at": "2026-09-13T21:45:00Z",
            "updated_at": "2026-09-13T21:45:00Z",
            "status": "active"
        }
        if body and isinstance(body, dict):
            response_item.update(body)
        elif schema_properties:
            response_item.update(_generate_mock_props(schema_properties, 1))
        else:
            response_item.update({
                "title": "New Sample Resource",
                "description": "Created via AgentFlow Mock Sandbox",
            })
        return response_item

    # 3. PUT / PATCH (Update)
    if method in ["PUT", "PATCH"]:
        response_item = {
            "id": str(uuid.uuid4()),
            "updated_at": "2026-09-13T21:45:00Z",
            "status": "updated"
        }
        if body and isinstance(body, dict):
            response_item.update(body)
        elif schema_properties:
            response_item.update(_generate_mock_props(schema_properties, 1))
        else:
            response_item["message"] = f"Resource {resource_name} modified successfully."
        return response_item

    # 4. GET Collection (List) vs Detail
    is_detail = any(part.startswith("{") or part.isdigit() or len(part) == 36 for part in clean_path)

    if is_detail:
        item = {
            "id": str(uuid.uuid4()),
            "created_at": "2026-09-10T12:00:00Z",
            "status": "active"
        }
        if schema_properties:
            item.update(_generate_mock_props(schema_properties, 1))
        else:
            item.update({
                "name": f"Sample {resource_name.capitalize()}",
                "description": f"Details for requested {resource_name} record.",
            })
        return item

    # List Collection
    items = []
    for i in range(1, 4):
        item = {
            "id": str(uuid.uuid4()),
            "created_at": f"2026-09-0{i}T10:00:00Z",
            "status": "active"
        }
        if schema_properties:
            item.update(_generate_mock_props(schema_properties, i))
        else:
            item.update({
                "name": f"{resource_name.capitalize()} #{i}",
                "description": f"Mock item #{i} generated by AgentFlow",
            })
        items.append(item)

    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": 20,
        "has_more": False
    }


def execute_mock_api_call(
    project_id: Union[UUID, str],
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Simulates an HTTP request against the project's generated API contracts.
    """
    if isinstance(project_id, str):
        try:
            target_id = UUID(project_id)
        except Exception:
            target_id = project_id
    else:
        target_id = project_id

    if db is None:
        raise ValueError("Database session required")

    project = db.query(Project).filter(Project.id == target_id).first()
    if not project:
        raise ValueError(f"Project '{project_id}' not found.")

    # Retrieve artifacts
    api_art = (
        db.query(ArtifactNode)
        .filter(ArtifactNode.project_id == target_id, ArtifactNode.artifact_type == "API_SPEC")
        .first()
    )
    db_art = (
        db.query(ArtifactNode)
        .filter(ArtifactNode.project_id == target_id, ArtifactNode.artifact_type == "DB_SCHEMA")
        .first()
    )

    api_text = "\n\n".join([s.content for s in api_art.sections if s.content]) if api_art and api_art.sections else ""
    db_text = "\n\n".join([s.content for s in db_art.sections if s.content]) if db_art and db_art.sections else ""

    routes = _extract_routes(api_text)
    schemas = _extract_schemas(db_text)

    # Normalize method and path
    req_method = method.upper()
    req_path = "/" + path.strip("/")

    # Find matching declared route
    matched_route = None
    for r in routes:
        if r["method"].upper() == req_method and _match_route_pattern(r["path"], req_path):
            matched_route = r
            break

    # Determine status code
    if matched_route:
        status_code = 201 if req_method == "POST" else 200
        route_desc = matched_route.get("description", "Declared endpoint")
    else:
        # Fallback simulation
        status_code = 201 if req_method == "POST" else 200
        route_desc = f"Simulated dynamic endpoint: {req_method} {req_path}"

    start_time = time.time()
    response_body = _synthesize_mock_response(req_method, req_path, schemas, body)
    latency_ms = max(12, int((time.time() - start_time) * 1000) + 18)

    return {
        "status_code": status_code,
        "status_text": "OK" if status_code == 200 else "Created",
        "method": req_method,
        "path": req_path,
        "matched_contract": bool(matched_route),
        "route_description": route_desc,
        "latency_ms": latency_ms,
        "response_headers": {
            "content-type": "application/json; charset=utf-8",
            "x-powered-by": "AgentFlow-Sandbox-Engine/1.0",
            "x-request-id": str(uuid.uuid4()),
            "x-ratelimit-remaining": "999",
            "server": "uvicorn/0.30.0"
        },
        "response_body": response_body,
        "available_routes_count": len(routes)
    }


def list_project_mock_routes(
    project_id: Union[UUID, str],
    db: Session
) -> List[Dict[str, Any]]:
    """
    Returns list of all available testable API routes parsed from the project's contracts.
    """
    if isinstance(project_id, str):
        try:
            target_id = UUID(project_id)
        except Exception:
            target_id = project_id
    else:
        target_id = project_id

    project = db.query(Project).filter(Project.id == target_id).first()
    if not project:
        raise ValueError(f"Project '{project_id}' not found.")

    api_art = (
        db.query(ArtifactNode)
        .filter(ArtifactNode.project_id == target_id, ArtifactNode.artifact_type == "API_SPEC")
        .first()
    )
    db_art = (
        db.query(ArtifactNode)
        .filter(ArtifactNode.project_id == target_id, ArtifactNode.artifact_type == "DB_SCHEMA")
        .first()
    )

    api_text = "\n\n".join([s.content for s in api_art.sections if s.content]) if api_art and api_art.sections else ""
    db_text = "\n\n".join([s.content for s in db_art.sections if s.content]) if db_art and db_art.sections else ""

    routes = _extract_routes(api_text)
    schemas = _extract_schemas(db_text)

    enhanced_routes = []
    for r in routes:
        m = r["method"].upper()
        p = r["path"]
        enhanced_routes.append({
            "method": m,
            "path": p,
            "description": r.get("description", ""),
            "sample_body": _synthesize_mock_response("POST", p, schemas) if m in ["POST", "PUT", "PATCH"] else None,
            "expected_status": 201 if m == "POST" else 200
        })

    return enhanced_routes
