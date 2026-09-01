"""
Phase 8+: OpenAPI 3.0.3 JSON Specification Generator

Parses the synchronized API_SPEC and DB_SCHEMA artifacts and constructs
a fully compliant, machine-readable OpenAPI 3.0.3 JSON specification
for Swagger UI, Postman, and automated client SDK generation.
"""

import re
from uuid import UUID
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from ..models import Project, ArtifactNode
from .scaffolder import sanitize_project_slug


def _extract_routes(api_text: str) -> List[Dict[str, Any]]:
    """Parses markdown endpoints into structured route dictionaries."""
    routes = []
    lines = api_text.splitlines()

    for line in lines:
        stripped = line.strip()
        # Match lines like `GET /api/v1/projects` or `### POST /auth/login`
        pattern = r"(?:###|##|-|\*|`|\b)(GET|POST|PUT|DELETE|PATCH)\s+([/a-zA-Z0-9_{}-]+)(?:`|\b)?(?:\s*[:-]\s*(.+))?"
        match = re.search(pattern, stripped, re.IGNORECASE)
        if match:
            method = match.group(1).upper()
            path = match.group(2)
            desc = match.group(3) if match.group(3) else f"{method} operation on {path}"
            
            # Avoid duplicate routes
            if not any(r["path"] == path and r["method"] == method for r in routes):
                routes.append({
                    "method": method,
                    "path": path,
                    "description": desc.strip("`* "),
                })

    if not routes:
        # Default standard endpoints
        routes = [
            {"method": "GET", "path": "/api/v1/health", "description": "System health and status check"},
            {"method": "GET", "path": "/api/v1/items", "description": "List all items with pagination"},
            {"method": "POST", "path": "/api/v1/items", "description": "Create and initialize a new item"},
            {"method": "GET", "path": "/api/v1/items/{id}", "description": "Retrieve specific item details by ID"},
            {"method": "PUT", "path": "/api/v1/items/{id}", "description": "Update item attributes"},
            {"method": "DELETE", "path": "/api/v1/items/{id}", "description": "Remove item record"},
        ]

    return routes


def _extract_schemas(db_text: str) -> Dict[str, Any]:
    """Parses DB tables into OpenAPI component schemas."""
    schemas = {}
    lines = db_text.splitlines()
    current_model = None

    for line in lines:
        stripped = line.strip()
        header_match = re.search(r"(?:###|##)\s*(?:Table:?\s*)?`?([a-zA-Z0-9_]+)`?", stripped, re.IGNORECASE)
        if header_match and not stripped.lower().startswith("## overview"):
            name = header_match.group(1).capitalize()
            if name.lower() not in ["table", "database", "schema", "overview", "relationships"]:
                current_model = name
                schemas[current_model] = {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "created_at": {"type": "string", "format": "date-time"}
                    }
                }
                continue

        if current_model and "|" in stripped:
            parts = [p.strip() for p in stripped.split("|") if p.strip()]
            if len(parts) >= 2 and not parts[0].startswith("---") and parts[0].lower() not in ["column", "field", "name"]:
                col_name = parts[0].replace("`", "")
                col_type = parts[1].replace("`", "").lower()
                
                json_type = "string"
                fmt = None
                if "int" in col_type:
                    json_type = "integer"
                elif "bool" in col_type:
                    json_type = "boolean"
                elif "float" in col_type or "numeric" in col_type:
                    json_type = "number"
                elif "uuid" in col_type:
                    json_type = "string"
                    fmt = "uuid"
                elif "time" in col_type or "date" in col_type:
                    json_type = "string"
                    fmt = "date-time"

                prop_def = {"type": json_type}
                if fmt:
                    prop_def["format"] = fmt
                schemas[current_model]["properties"][col_name] = prop_def

    if not schemas:
        schemas = {
            "Item": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"}
                }
            }
        }

    return schemas


def generate_openapi_spec(project_id: UUID, db: Session) -> Dict[str, Any]:
    """
    Constructs a complete OpenAPI 3.0.3 specification JSON from project artifacts.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    api_node = next((n for n in project.artifact_nodes if n.artifact_type == "API_SPEC"), None)
    db_node = next((n for n in project.artifact_nodes if n.artifact_type == "DB_SCHEMA"), None)

    api_text = "\n\n".join(s.content for s in api_node.sections) if api_node and api_node.sections else ""
    db_text = "\n\n".join(s.content for s in db_node.sections) if db_node and db_node.sections else ""

    routes = _extract_routes(api_text)
    schemas = _extract_schemas(db_text)

    paths: Dict[str, Any] = {}
    for r in routes:
        path = r["path"]
        method = r["method"].lower()
        if path not in paths:
            paths[path] = {}

        # Extract path parameters
        path_params = re.findall(r"\{([a-zA-Z0-9_]+)\}", path)
        parameters = [
            {
                "name": p,
                "in": "path",
                "required": True,
                "schema": {"type": "string"}
            }
            for p in path_params
        ]

        operation: Dict[str, Any] = {
            "summary": r["description"],
            "description": f"Automated OpenAPI endpoint generated by AgentFlow for {project.name}.",
            "responses": {
                "200": {
                    "description": "Successful operation",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "status": {"type": "string", "example": "success"},
                                    "data": {"type": "object"}
                                }
                            }
                        }
                    }
                },
                "400": {"description": "Invalid input parameters"},
                "404": {"description": "Resource not found"}
            }
        }

        if parameters:
            operation["parameters"] = parameters

        if method in ["post", "put", "patch"]:
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "payload": {"type": "object"}
                            }
                        }
                    }
                }
            }

        paths[path][method] = operation

    return {
        "openapi": "3.0.3",
        "info": {
            "title": f"{project.name} API",
            "description": project.brief,
            "version": "1.0.0",
            "contact": {
                "name": "AgentFlow Autonomous Engineering Fleet",
                "url": "https://github.com/AgentFlow"
            }
        },
        "servers": [
            {"url": "http://localhost:8000", "description": "Local Development Server"},
            {"url": "https://api.agentflow.dev", "description": "Production Cloud Gateway"}
        ],
        "paths": paths,
        "components": {
            "schemas": schemas,
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                }
            }
        }
    }
