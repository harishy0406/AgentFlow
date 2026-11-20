"""
Phase 22: Bruno Git-Friendly API Collection Generator Engine

Transforms synchronized API_SPEC and DB_SCHEMA artifacts into a fully compliant
Bruno collection structure (https://usebruno.com) with:
- bruno.json manifest
- environments/local.bru and environments/production.bru
- collection.bru
- Individual .bru HTTP request definitions with headers, sample bodies, and assertions
- Exportable Bruno JSON specification and downloadable in-memory ZIP package
"""

import io
import json
import re
import uuid
import zipfile
from typing import Dict, Any, List, Union
from uuid import UUID
from sqlalchemy.orm import Session

try:
    from ..models import Project, ArtifactNode
    from .openapi_generator import _extract_routes, _extract_schemas
    from .scaffolder import sanitize_project_slug
except ImportError:
    from app.models import Project, ArtifactNode
    from app.agents.openapi_generator import _extract_routes, _extract_schemas
    from app.agents.scaffolder import sanitize_project_slug


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", (text or "").lower())
    slug = re.sub(r"[-\s]+", "-", cleaned).strip("-")
    return slug or "agentflow-app"


def _generate_sample_body_dict(method: str, path: str, schemas: Dict[str, Any]) -> Dict[str, Any]:
    if method not in ["POST", "PUT", "PATCH"]:
        return {}

    matched_schema = None
    for model_name, schema in schemas.items():
        if model_name.lower() in path.lower():
            matched_schema = schema
            break

    if matched_schema and "properties" in matched_schema:
        payload: Dict[str, Any] = {}
        for prop, pdef in matched_schema["properties"].items():
            if prop in ["id", "created_at", "updated_at"]:
                continue
            ptype = pdef.get("type", "string")
            if ptype == "integer":
                payload[prop] = 101
            elif ptype == "boolean":
                payload[prop] = True
            elif ptype == "number":
                payload[prop] = 49.99
            elif ptype == "string":
                if "email" in prop:
                    payload[prop] = "dev@agentflow.io"
                elif "name" in prop or "title" in prop:
                    payload[prop] = f"Sample {prop.capitalize()}"
                elif "status" in prop or "state" in prop:
                    payload[prop] = "active"
                else:
                    payload[prop] = f"sample_{prop}"
        if payload:
            return payload

    return {
        "title": "New Sample Resource",
        "status": "active",
        "description": "Generated via AgentFlow Bruno Engine",
    }


def _format_bru_file(
    name: str,
    method: str,
    path: str,
    seq: int,
    body_dict: Dict[str, Any],
) -> str:
    """Formats an individual Bruno .bru declarative request file."""
    clean_method = method.lower()
    has_body = clean_method in ["post", "put", "patch"] and bool(body_dict)
    body_type = "json" if has_body else "none"

    lines = [
        "meta {",
        f"  name: {name}",
        "  type: http",
        f"  seq: {seq}",
        "}",
        "",
        f"{clean_method} {{",
        f"  url: {{{{baseUrl}}}}{path}",
        f"  body: {body_type}",
        "  auth: none",
        "}",
        "",
        "headers {",
        "  Content-Type: application/json",
        "  Accept: application/json",
        "}",
    ]

    if has_body:
        lines.extend([
            "",
            "body:json {",
            json.dumps(body_dict, indent=2),
            "}",
        ])

    expected_status = 201 if clean_method == "post" else 200
    lines.extend([
        "",
        "assert {",
        f"  res.status: eq {expected_status}",
        "  res.body: isDefined",
        "}",
    ])

    return "\n".join(lines) + "\n"


def generate_bruno_collection(project_id: Union[UUID, str], db: Session) -> Dict[str, Any]:
    """
    Generates a full Bruno collection directory structure and JSON representation.
    """
    target_id = UUID(str(project_id))
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

    api_text = ""
    if api_art and api_art.sections:
        api_text = "\n\n".join([s.content for s in api_art.sections if s.content])

    db_text = ""
    if db_art and db_art.sections:
        db_text = "\n\n".join([s.content for s in db_art.sections if s.content])

    routes = _extract_routes(api_text)
    schemas = _extract_schemas(db_text)

    slug = _slugify(project.name)
    coll_name = f"{project.name} API"

    # Manifest: bruno.json
    bruno_manifest = {
        "version": "1",
        "name": coll_name,
        "type": "collection",
        "ignore": [
            "node_modules",
            ".git",
        ],
    }

    env_local = """vars {
  baseUrl: http://localhost:8000
}
"""

    env_prod = f"""vars {{
  baseUrl: https://{slug}.agentflow.internal
}}
"""

    coll_bru = f"""meta {{
  name: {coll_name}
}}
"""

    files: Dict[str, str] = {
        f"{slug}-bruno/bruno.json": json.dumps(bruno_manifest, indent=2) + "\n",
        f"{slug}-bruno/collection.bru": coll_bru,
        f"{slug}-bruno/environments/local.bru": env_local,
        f"{slug}-bruno/environments/production.bru": env_prod,
    }

    folders_set = set()
    requests_list = []
    seq_counter = 1

    for r in routes:
        method = r["method"].upper()
        path = r["path"]
        desc = r.get("description", f"{method} {path}")

        path_segments = [
            p for p in path.strip("/").split("/")
            if p and not p.startswith("{") and p not in ["api", "v1", "v2"]
        ]
        folder_tag = path_segments[0].lower() if path_segments else "general"
        folders_set.add(folder_tag)

        clean_path_slug = re.sub(r"[^\w-]", "", path.replace("/", "-")).strip("-")
        req_filename = f"{method.lower()}-{clean_path_slug or 'root'}.bru"
        file_path = f"{slug}-bruno/requests/{folder_tag}/{req_filename}"

        body_dict = _generate_sample_body_dict(method, path, schemas)
        req_name = f"{method} {path}"

        bru_content = _format_bru_file(
            name=req_name,
            method=method,
            path=path,
            seq=seq_counter,
            body_dict=body_dict,
        )
        files[file_path] = bru_content

        requests_list.append({
            "name": req_name,
            "method": method,
            "path": path,
            "folder": folder_tag,
            "seq": seq_counter,
            "sample_body": body_dict,
            "file_path": file_path,
        })
        seq_counter += 1

    return {
        "project_id": str(project.id),
        "project_name": project.name,
        "collection_name": coll_name,
        "slug": slug,
        "requests_count": len(requests_list),
        "folders_count": len(folders_set),
        "environments": ["local", "production"],
        "files_count": len(files),
        "files": files,
        "requests": requests_list,
    }


def generate_bruno_zip(bundle: Dict[str, Any]) -> bytes:
    """
    Packs the Bruno collection directory into an in-memory ZIP archive.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path, content in bundle.get("files", {}).items():
            zf.writestr(file_path, content)
    buffer.seek(0)
    return buffer.getvalue()
