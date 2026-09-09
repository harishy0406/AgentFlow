"""
Phase 8+: Postman Collection v2.1.0 Generator Engine

Transforms synchronized API_SPEC and DB_SCHEMA artifacts into a fully compliant
Postman Collection v2.1.0 schema with pre-configured requests, environment variables,
sample payloads, and automated test assertion scripts.
"""

import re
import json
import uuid
from uuid import UUID
from typing import Dict, Any, List, Union
from sqlalchemy.orm import Session

from ..models import Project, ArtifactNode
from .openapi_generator import _extract_routes, _extract_schemas


def _generate_sample_body(method: str, path: str, schemas: Dict[str, Any]) -> str:
    """Constructs realistic JSON request body for POST/PUT/PATCH methods."""
    if method not in ["POST", "PUT", "PATCH"]:
        return ""

    # Find matching schema if path matches a model name
    matched_schema = None
    for model_name, schema in schemas.items():
        if model_name.lower() in path.lower():
            matched_schema = schema
            break

    if matched_schema and "properties" in matched_schema:
        payload = {}
        for prop, pdef in matched_schema["properties"].items():
            if prop in ["id", "created_at", "updated_at"]:
                continue
            ptype = pdef.get("type", "string")
            if ptype == "integer":
                payload[prop] = 100
            elif ptype == "boolean":
                payload[prop] = True
            elif ptype == "number":
                payload[prop] = 49.99
            elif ptype == "string":
                if "email" in prop:
                    payload[prop] = "user@agentflow.io"
                elif "name" in prop or "title" in prop:
                    payload[prop] = f"Sample {prop.capitalize()}"
                elif "desc" in prop:
                    payload[prop] = "Automated test description from AgentFlow"
                else:
                    payload[prop] = f"sample_{prop}_val"
        return json.dumps(payload, indent=2)

    # Fallback standard mock payload
    return json.dumps({
        "title": "New Sample Resource",
        "description": "Generated via AgentFlow Postman Engine",
        "status": "active"
    }, indent=2)


def generate_postman_collection(project_id: Union[UUID, str], db: Session) -> Dict[str, Any]:
    """
    Generates a complete Postman Collection v2.1.0 specification for the project.
    """
    if isinstance(project_id, str):
        try:
            target_id = uuid.UUID(project_id)
        except Exception:
            target_id = project_id
    else:
        target_id = project_id

    project = db.query(Project).filter(Project.id == target_id).first()
    if not project:
        raise ValueError(f"Project '{project_id}' not found.")

    # Retrieve API_SPEC and DB_SCHEMA artifacts
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

    api_text = ""
    if api_art and api_art.sections:
        api_text = "\n\n".join([s.content for s in api_art.sections if s.content])

    db_text = ""
    if db_art and db_art.sections:
        db_text = "\n\n".join([s.content for s in db_art.sections if s.content])

    routes = _extract_routes(api_text)
    schemas = _extract_schemas(db_text)

    # Group routes by root path tag (e.g. /api/v1/projects -> Projects)
    grouped_items: Dict[str, List[Dict[str, Any]]] = {}

    for route in routes:
        method = route["method"]
        path = route["path"]
        desc = route["description"]

        # Parse folder tag from path
        path_segments = [p for p in path.strip("/").split("/") if p and not p.startswith("{") and p not in ["api", "v1", "v2"]]
        folder_tag = path_segments[0].capitalize() if path_segments else "General"

        # Construct Postman URL parts
        clean_path = path.lstrip("/")
        path_parts = clean_path.split("/")
        
        url_obj = {
            "raw": "{{baseUrl}}/" + clean_path,
            "host": ["{{baseUrl}}"],
            "path": path_parts,
            "query": []
        }

        # Check for query params in GET lists
        if method == "GET" and not any(p.startswith("{") for p in path_parts):
            url_obj["query"] = [
                {"key": "page", "value": "1", "description": "Pagination page number"},
                {"key": "limit", "value": "20", "description": "Items per page limit"}
            ]

        # Construct Headers
        headers = [
            {"key": "Content-Type", "value": "application/json", "type": "text"},
            {"key": "Authorization", "value": "Bearer {{bearerToken}}", "type": "text"}
        ]

        # Request Object
        request_obj: Dict[str, Any] = {
            "method": method,
            "header": headers,
            "url": url_obj,
            "description": desc
        }

        # Add Request Body for mutation methods
        if method in ["POST", "PUT", "PATCH"]:
            body_content = _generate_sample_body(method, path, schemas)
            request_obj["body"] = {
                "mode": "raw",
                "raw": body_content,
                "options": {
                    "raw": {
                        "language": "json"
                    }
                }
            }

        # Test script assertions
        expected_status = 201 if method == "POST" else 200
        test_script = [
            f"pm.test(\"Status code is {expected_status}\", function () {{",
            f"    pm.response.to.have.status({expected_status});",
            "});",
            "pm.test(\"Response time is acceptable (<500ms)\", function () {",
            "    pm.expect(pm.response.responseTime).to.be.below(500);",
            "});",
            "pm.test(\"Response has valid JSON format\", function () {",
            "    pm.response.to.be.json;",
            "});"
        ]

        postman_item = {
            "name": f"{method} {path}",
            "request": request_obj,
            "response": [],
            "event": [
                {
                    "listen": "test",
                    "script": {
                        "type": "text/javascript",
                        "exec": test_script
                    }
                }
            ]
        }

        if folder_tag not in grouped_items:
            grouped_items[folder_tag] = []
        grouped_items[folder_tag].append(postman_item)

    # Convert folder dictionary to Postman item array
    collection_items = []
    for folder_name, items in grouped_items.items():
        collection_items.append({
            "name": folder_name,
            "item": items,
            "description": f"Endpoints and operations for {folder_name} resources"
        })

    collection = {
        "info": {
            "_postman_id": str(uuid.uuid4()),
            "name": f"{project.name} API Collection",
            "description": f"Automated Postman Collection generated by AgentFlow for '{project.name}'.\n\n{project.brief}",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "version": "1.0.0"
        },
        "item": collection_items,
        "variable": [
            {
                "key": "baseUrl",
                "value": "http://localhost:8000",
                "type": "string",
                "description": "Base URL of the running API server"
            },
            {
                "key": "bearerToken",
                "value": "ey...sample_jwt_token_for_auth",
                "type": "string",
                "description": "JWT Bearer access token"
            }
        ]
    }

    return collection
