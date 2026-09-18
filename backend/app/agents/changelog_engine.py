"""
Phase 11: AI-Powered Semantic API Changelog & Breaking Change Detector Engine

Analyzes API specification deltas, detects breaking contract modifications,
calculates Semantic Versioning (SemVer) increments, and generates standard
Keep-a-Changelog release documentation.
"""

import re
from datetime import datetime, timezone
from uuid import UUID
from typing import Dict, Any, List, Union, Optional
from sqlalchemy.orm import Session

from ..models import Project, ArtifactNode, ArtifactSection
from .scaffolder import sanitize_project_slug
from .openapi_generator import _extract_routes


def _parse_route_map(api_text: str) -> Dict[str, Dict[str, Any]]:
    """Extracts a normalized route dictionary keyed by METHOD:PATH."""
    routes = _extract_routes(api_text)
    route_map = {}
    for r in routes:
        m = r["method"].upper()
        p = r["path"].strip()
        key = f"{m}:{p}"
        # Extract path parameters
        params = re.findall(r"\{([a-zA-Z0-9_]+)\}", p)
        route_map[key] = {
            "method": m,
            "path": p,
            "description": r.get("description", ""),
            "params": params,
        }
    return route_map


def compare_api_specs(
    previous_api_text: str,
    updated_api_text: str
) -> List[Dict[str, Any]]:
    """
    Compares two versions of an API specification and classifies each change
    as BREAKING, NON_BREAKING_ADD, DEPRECATION, or MODIFICATION.
    """
    old_map = _parse_route_map(previous_api_text)
    new_map = _parse_route_map(updated_api_text)

    changes: List[Dict[str, Any]] = []

    # 1. Check for Deleted Endpoints (BREAKING)
    for old_key, old_route in old_map.items():
        if old_key not in new_map:
            # Check if same path exists with different method
            same_path_diff_method = [k for k in new_map if k.split(":")[-1] == old_route["path"]]
            if same_path_diff_method:
                changes.append({
                    "category": "BREAKING",
                    "endpoint": old_route["path"],
                    "method": old_route["method"],
                    "description": f"HTTP Method altered from {old_route['method']} to {same_path_diff_method[0].split(':')[0]}.",
                    "impact": "HIGH",
                    "remediation": f"Keep existing {old_route['method']} endpoint as deprecated alias until client SDKs migrate."
                })
            else:
                changes.append({
                    "category": "BREAKING",
                    "endpoint": old_route["path"],
                    "method": old_route["method"],
                    "description": f"Endpoint removed: {old_route['method']} {old_route['path']}",
                    "impact": "HIGH",
                    "remediation": f"Implement backwards-compatible HTTP 308 Permanent Redirect or fallback routing handler."
                })

    # 2. Check for Added or Modified Endpoints
    for new_key, new_route in new_map.items():
        if new_key not in old_map:
            # New Endpoint added
            changes.append({
                "category": "NON_BREAKING_ADD",
                "endpoint": new_route["path"],
                "method": new_route["method"],
                "description": f"New endpoint added: {new_route['method']} {new_route['path']} ({new_route['description']})",
                "impact": "LOW",
                "remediation": None
            })
        else:
            old_route = old_map[new_key]
            # Check if new mandatory path parameters were introduced
            new_params = set(new_route["params"])
            old_params = set(old_route["params"])
            added_params = new_params - old_params

            if added_params:
                changes.append({
                    "category": "BREAKING",
                    "endpoint": new_route["path"],
                    "method": new_route["method"],
                    "description": f"New mandatory path parameters added: {', '.join(added_params)}.",
                    "impact": "HIGH",
                    "remediation": "Provide default fallback values or query parameters instead of mandatory path segments."
                })
            elif "deprecated" in new_route["description"].lower():
                changes.append({
                    "category": "DEPRECATION",
                    "endpoint": new_route["path"],
                    "method": new_route["method"],
                    "description": f"Endpoint marked for deprecation: {new_route['method']} {new_route['path']}.",
                    "impact": "MEDIUM",
                    "remediation": "Send Deprecation and Sunset HTTP headers in the API response."
                })
            elif old_route["description"] != new_route["description"]:
                changes.append({
                    "category": "MODIFICATION",
                    "endpoint": new_route["path"],
                    "method": new_route["method"],
                    "description": f"Documentation updated for {new_route['method']} {new_route['path']}.",
                    "impact": "LOW",
                    "remediation": None
                })

    return changes


def calculate_semver_bump(
    current_version: str,
    changes: List[Dict[str, Any]]
) -> Dict[str, str]:
    """Calculates Semantic Versioning bump based on detected API change impacts."""
    # Parse current version or fallback to 1.0.0
    v_match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", current_version.strip())
    if v_match:
        major, minor, patch = int(v_match.group(1)), int(v_match.group(2)), int(v_match.group(3))
    else:
        major, minor, patch = 1, 0, 0

    has_breaking = any(c["category"] == "BREAKING" for c in changes)
    has_adds = any(c["category"] in ["NON_BREAKING_ADD", "DEPRECATION"] for c in changes)

    if has_breaking:
        bump_type = "MAJOR"
        suggested = f"v{major + 1}.0.0"
        rationale = "Breaking API modifications detected (removed endpoints, changed HTTP verbs, or new mandatory parameters)."
    elif has_adds:
        bump_type = "MINOR"
        suggested = f"v{major}.{minor + 1}.0"
        rationale = "Backwards-compatible additions or deprecation notices introduced without breaking existing clients."
    else:
        bump_type = "PATCH"
        suggested = f"v{major}.{minor}.{patch + 1}"
        rationale = "Internal modifications or documentation refinements with zero contract changes."

    return {
        "current_version": f"v{major}.{minor}.{patch}",
        "suggested_version": suggested,
        "bump_type": bump_type,
        "rationale": rationale
    }


def generate_keep_a_changelog_markdown(
    project_name: str,
    semver: Dict[str, str],
    changes: List[Dict[str, Any]]
) -> str:
    """Formats Keep-a-Changelog compliant release notes."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target_ver = semver["suggested_version"]

    breaking = [c for c in changes if c["category"] == "BREAKING"]
    adds = [c for c in changes if c["category"] == "NON_BREAKING_ADD"]
    deps = [c for c in changes if c["category"] == "DEPRECATION"]
    mods = [c for c in changes if c["category"] == "MODIFICATION"]

    lines = [
        f"# Changelog — {project_name}",
        "",
        f"All notable changes to this project are documented here following [Keep a Changelog](https://keepachangelog.com/).",
        "",
        f"## [{target_ver}] - {today}",
        f"**Semantic Bump:** `{semver['bump_type']}` — {semver['rationale']}",
        ""
    ]

    if breaking:
        lines.append("### 🚨 Breaking Changes")
        for b in breaking:
            lines.append(f"- **`{b['method']} {b['endpoint']}`**: {b['description']}")
            if b.get("remediation"):
                lines.append(f"  - *Remediation:* {b['remediation']}")
        lines.append("")

    if adds:
        lines.append("### 🚀 Added")
        for a in adds:
            lines.append(f"- **`{a['method']} {a['endpoint']}`**: {a['description']}")
        lines.append("")

    if deps:
        lines.append("### ⚠️ Deprecated")
        for d in deps:
            lines.append(f"- **`{d['method']} {d['endpoint']}`**: {d['description']}")
        lines.append("")

    if mods:
        lines.append("### 🔄 Changed")
        for m in mods:
            lines.append(f"- **`{m['method']} {m['endpoint']}`**: {m['description']}")
        lines.append("")

    if not changes:
        lines.append("### ℹ️ No Contract Changes")
        lines.append("- API contract matches baseline specification exactly.")
        lines.append("")

    return "\n".join(lines)


def generate_project_changelog(
    project_id: Union[UUID, str],
    db: Session,
    target_api_spec: Optional[str] = None
) -> Dict[str, Any]:
    """Generates a complete semantic changelog and breaking change report for a project."""
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

    api_node = next((n for n in project.artifact_nodes if n.artifact_type == "API_SPEC"), None)
    current_api_text = "\n\n".join(s.content for s in api_node.sections) if api_node and api_node.sections else ""

    # Baseline comparison (if no target provided, compare against default baseline CRUD)
    if target_api_spec:
        old_spec = current_api_text
        new_spec = target_api_spec
    else:
        # Standard synthetic comparison demonstrating evolution from v1.0.0
        old_spec = (
            "GET /api/v1/health - Health check\n"
            "GET /api/v1/items - List all items\n"
            "POST /api/v1/items - Create item\n"
            "GET /api/v1/items/{id} - Get item by ID\n"
            "DELETE /api/v1/items/{id} - Delete item\n"
        )
        new_spec = current_api_text if current_api_text else old_spec

    changes = compare_api_specs(old_spec, new_spec)
    breaking_count = sum(1 for c in changes if c["category"] == "BREAKING")
    semver = calculate_semver_bump("v1.0.0", changes)
    markdown_changelog = generate_keep_a_changelog_markdown(project.name, semver, changes)

    release_notes = f"""# Release Notes {semver['suggested_version']} for {project.name}
Recommended SemVer Bump: {semver['bump_type']}

Total API Contract Modifications: {len(changes)}
Breaking Contract Deltas: {breaking_count}

{markdown_changelog}
"""

    return {
        "project_id": project.id,
        "project_name": project.name,
        "version_tag": semver["suggested_version"],
        "semver": semver,
        "breaking_changes_count": breaking_count,
        "total_changes_count": len(changes),
        "changes": changes,
        "markdown_changelog": markdown_changelog,
        "release_notes": release_notes,
    }
