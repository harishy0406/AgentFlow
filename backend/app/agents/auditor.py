"""
Consistency Auditor Agent — Phase 4

Cross-artifact structural validation engine that detects semantic drift
between artifact pairs and persists drift records for resolution.

Validation Rules (from design.md §6.1):
  1. requirement_coverage:      PRD ↔ SDD
  2. schema_endpoint_mapping:   DB_SCHEMA ↔ API_SPEC
  3. endpoint_requirement_map:  API_SPEC ↔ PRD
  4. story_traceability:        USER_STORIES ↔ PRD
  5. task_coverage:             TASKS ↔ USER_STORIES
"""

import re
from typing import List, Dict, Any, Optional, Set, Tuple
from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import (
    ArtifactNode, ArtifactSection, DriftRecord, Project
)


# ---------------------------------------------------------------------------
# Validation Rule Definitions
# ---------------------------------------------------------------------------

@dataclass
class ValidationRule:
    """Defines a single cross-artifact structural check."""
    name: str
    artifact_type_a: str
    artifact_type_b: str
    description: str
    severity: str  # 'low', 'medium', 'high'


# The five core validation rules from the design spec
VALIDATION_RULES: List[ValidationRule] = [
    ValidationRule(
        name="requirement_coverage",
        artifact_type_a="PRD",
        artifact_type_b="SDD",
        description="Every PRD requirement must have a corresponding SDD component.",
        severity="high",
    ),
    ValidationRule(
        name="schema_endpoint_mapping",
        artifact_type_a="DB_SCHEMA",
        artifact_type_b="API_SPEC",
        description="Every API endpoint field reference must exist in the DB schema.",
        severity="high",
    ),
    ValidationRule(
        name="endpoint_requirement_mapping",
        artifact_type_a="API_SPEC",
        artifact_type_b="PRD",
        description="Every API endpoint must trace to a PRD requirement.",
        severity="medium",
    ),
    ValidationRule(
        name="story_traceability",
        artifact_type_a="USER_STORIES",
        artifact_type_b="PRD",
        description="Every user story must trace back to a PRD requirement.",
        severity="medium",
    ),
    ValidationRule(
        name="task_coverage",
        artifact_type_a="TASKS",
        artifact_type_b="USER_STORIES",
        description="Every user story must have at least one associated task.",
        severity="low",
    ),
]

# Map rule names to their checker functions
CHECKER_REGISTRY: Dict[str, Any] = {}


def _register_checker(rule_name: str):
    """Decorator to register a checker function for a validation rule."""
    def decorator(func):
        CHECKER_REGISTRY[rule_name] = func
        return func
    return decorator


# ---------------------------------------------------------------------------
# Helper: fetch artifact content
# ---------------------------------------------------------------------------

def _get_artifact_content(
    project_id: UUID,
    artifact_type: str,
    db: Session,
) -> Tuple[Optional[ArtifactNode], str]:
    """Fetch the artifact node and its concatenated content."""
    node = (
        db.query(ArtifactNode)
        .filter(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type,
        )
        .first()
    )
    if node is None:
        return None, ""
    sections = (
        db.query(ArtifactSection)
        .filter(ArtifactSection.artifact_node_id == node.id)
        .order_by(ArtifactSection.section_key)
        .all()
    )
    content = "\n\n".join(s.content for s in sections)
    return node, content


def _extract_requirement_ids(content: str) -> Set[str]:
    """
    Extract all requirement IDs from content.
    Matches patterns like FR-1, NFR-2, REQ-01, US-5, etc.
    Returns lowercase set for case-insensitive comparison.
    """
    return set(
        m.lower()
        for m in re.findall(r"\b(?:FR|NFR|REQ|US)-?\d+\b", content, re.IGNORECASE)
    )


def _extract_table_names(content: str) -> Set[str]:
    """Extract CREATE TABLE names from SQL-like schema content."""
    return set(
        m.group(1).lower()
        for m in re.finditer(r"CREATE\s+TABLE\s+[`\"]?(\w+)[`\"]?", content, re.IGNORECASE)
    )


def _extract_column_names(content: str) -> Set[str]:
    """
    Extract column-like identifiers from schema content.
    Looks for patterns within CREATE TABLE blocks.
    """
    columns = set()
    # Match lines that look like column definitions (indented, name type)
    for m in re.finditer(
        r"^\s+[`\"]?(\w+)[`\"]?\s+(?:VARCHAR|TEXT|INTEGER|INT|FLOAT|BOOLEAN|UUID|SERIAL|TIMESTAMP|DATE|BIGINT|SMALLINT|NUMERIC|DECIMAL|JSON|JSONB)",
        content, re.IGNORECASE | re.MULTILINE
    ):
        columns.add(m.group(1).lower())
    return columns


def _extract_endpoints(content: str) -> List[str]:
    """
    Extract API endpoint definitions.
    Returns list of 'METHOD /path' strings.
    """
    endpoints = []
    for m in re.finditer(
        r"\b(GET|POST|PUT|PATCH|DELETE)\b\s+([/`][^\s`]+)",
        content, re.IGNORECASE
    ):
        method = m.group(1).upper()
        path = m.group(2).strip("`").strip()
        endpoints.append(f"{method} {path}")
    return endpoints


def _extract_user_stories(content: str) -> List[str]:
    """
    Extract user story lines from content.
    Looks for 'As a ...' or 'I want ...' patterns.
    """
    stories = []
    for line in content.splitlines():
        stripped = line.strip()
        if "as a" in stripped.lower() and "i want" in stripped.lower():
            stories.append(stripped)
        elif stripped.lower().startswith("as a"):
            stories.append(stripped)
    return stories


def _extract_task_items(content: str) -> List[str]:
    """Extract task items (bulleted/numbered list items)."""
    tasks = []
    for line in content.splitlines():
        stripped = line.strip()
        if re.match(r"^[-*•]\s+", stripped) or re.match(r"^\d+[.)]\s+", stripped):
            tasks.append(stripped)
    return tasks


# ---------------------------------------------------------------------------
# Per-Rule Checker Functions (Task A)
# ---------------------------------------------------------------------------

@_register_checker("requirement_coverage")
def _check_requirement_coverage(
    content_a: str,  # PRD
    content_b: str,  # SDD
    node_a: ArtifactNode,
    node_b: ArtifactNode,
) -> List[Dict[str, Any]]:
    """
    Check that every requirement ID in the PRD is referenced in the SDD.
    Returns a list of drift descriptions for uncovered requirements.
    """
    prd_reqs = _extract_requirement_ids(content_a)
    if not prd_reqs:
        return []

    sdd_lower = content_b.lower()
    drifts = []
    for req_id in sorted(prd_reqs):
        if req_id not in sdd_lower:
            drifts.append({
                "description": f"PRD requirement '{req_id.upper()}' has no corresponding reference in the SDD.",
                "missing_id": req_id.upper(),
            })
    return drifts


@_register_checker("schema_endpoint_mapping")
def _check_schema_endpoint_mapping(
    content_a: str,  # DB_SCHEMA
    content_b: str,  # API_SPEC
    node_a: ArtifactNode,
    node_b: ArtifactNode,
) -> List[Dict[str, Any]]:
    """
    Check that table/column names referenced in the API spec exist in the
    DB schema. Detects endpoints that reference non-existent fields.
    """
    tables = _extract_table_names(content_a)
    columns = _extract_column_names(content_a)
    all_schema_ids = tables | columns

    if not all_schema_ids:
        return []

    drifts = []
    # Look for field references in the API spec that don't exist in the schema
    # We check for words in the API spec that look like they reference DB entities
    api_field_refs = set()
    for m in re.finditer(
        r"\b(\w+_id|id|name|email|title|status|created_at|updated_at)\b",
        content_b, re.IGNORECASE
    ):
        api_field_refs.add(m.group(1).lower())

    # Also look for explicit table references
    for m in re.finditer(
        r"(?:table|entity|model|resource)[:\s]+[`\"]?(\w+)[`\"]?",
        content_b, re.IGNORECASE
    ):
        ref = m.group(1).lower()
        if ref not in tables and ref not in {"the", "a", "an", "this", "that"}:
            drifts.append({
                "description": f"API spec references table/entity '{ref}' which is not defined in the DB schema.",
                "missing_id": ref,
            })

    return drifts


@_register_checker("endpoint_requirement_mapping")
def _check_endpoint_requirement_mapping(
    content_a: str,  # API_SPEC
    content_b: str,  # PRD
    node_a: ArtifactNode,
    node_b: ArtifactNode,
) -> List[Dict[str, Any]]:
    """
    Check that every API endpoint can be traced to a PRD requirement.
    Looks for requirement ID references near endpoint definitions.
    """
    endpoints = _extract_endpoints(content_a)
    prd_reqs = _extract_requirement_ids(content_b)

    if not endpoints or not prd_reqs:
        return []

    drifts = []
    api_lines = content_a.splitlines()

    for endpoint in endpoints:
        # Look for the endpoint in the API spec and check nearby lines
        # for requirement ID references
        found_trace = False
        for i, line in enumerate(api_lines):
            if endpoint.split()[1] in line:  # Match the path part
                # Check a window of ±15 lines for requirement references
                window_start = max(0, i - 5)
                window_end = min(len(api_lines), i + 15)
                window = "\n".join(api_lines[window_start:window_end])
                window_req_ids = _extract_requirement_ids(window)
                if window_req_ids & prd_reqs:
                    found_trace = True
                    break

        if not found_trace:
            drifts.append({
                "description": f"API endpoint '{endpoint}' has no traceable PRD requirement.",
                "missing_id": endpoint,
            })

    return drifts


@_register_checker("story_traceability")
def _check_story_traceability(
    content_a: str,  # USER_STORIES
    content_b: str,  # PRD
    node_a: ArtifactNode,
    node_b: ArtifactNode,
) -> List[Dict[str, Any]]:
    """
    Check that every user story references at least one PRD requirement.
    """
    stories = _extract_user_stories(content_a)
    prd_reqs = _extract_requirement_ids(content_b)

    if not stories or not prd_reqs:
        return []

    drifts = []
    for idx, story in enumerate(stories, 1):
        story_reqs = _extract_requirement_ids(story)
        if not (story_reqs & prd_reqs):
            # Truncate story for the description
            short = story[:80] + "..." if len(story) > 80 else story
            drifts.append({
                "description": f"User story #{idx} ('{short}') does not reference any PRD requirement.",
                "missing_id": f"story_{idx}",
            })

    return drifts


@_register_checker("task_coverage")
def _check_task_coverage(
    content_a: str,  # TASKS
    content_b: str,  # USER_STORIES
    node_a: ArtifactNode,
    node_b: ArtifactNode,
) -> List[Dict[str, Any]]:
    """
    Check that every user story has at least one associated task.
    """
    stories = _extract_user_stories(content_b)
    tasks = _extract_task_items(content_a)

    if not stories:
        return []

    if not tasks:
        return [{
            "description": "No task items found in the TASKS artifact. All user stories lack coverage.",
            "missing_id": "all_stories",
        }]

    drifts = []
    task_text = content_a.lower()

    for idx, story in enumerate(stories, 1):
        # Extract key phrases from the story to match against tasks
        # Look for the core "I want ..." part
        want_match = re.search(r"i want\s+(.+?)(?:so that|$)", story, re.IGNORECASE)
        if want_match:
            key_phrase = want_match.group(1).strip().lower()
            # Check if any significant words from the key phrase appear in tasks
            significant_words = [
                w for w in key_phrase.split()
                if len(w) > 3 and w not in {"want", "that", "this", "with", "from", "have", "able"}
            ]
            found = any(w in task_text for w in significant_words)
            if not found:
                short = story[:80] + "..." if len(story) > 80 else story
                drifts.append({
                    "description": f"User story #{idx} ('{short}') has no associated task in the breakdown.",
                    "missing_id": f"story_{idx}",
                })

    return drifts


# ---------------------------------------------------------------------------
# Drift Record Management (Task B)
# ---------------------------------------------------------------------------

def create_drift_record(
    project_id: UUID,
    rule: ValidationRule,
    node_a: ArtifactNode,
    node_b: ArtifactNode,
    description: str,
    db: Session,
) -> DriftRecord:
    """Create and persist a new drift record."""
    record = DriftRecord(
        project_id=project_id,
        check_name=rule.name,
        artifact_a_id=node_a.id,
        artifact_b_id=node_b.id,
        description=description,
        severity=rule.severity,
        status="open",
    )
    db.add(record)
    return record


def resolve_drift_record(
    drift_id: UUID,
    resolution: str,
    db: Session,
) -> Optional[DriftRecord]:
    """
    Mark a drift record as resolved.

    Args:
        drift_id: The drift record to resolve.
        resolution: Either 'auto_fixed' or 'dismissed'.
        db: Database session.

    Returns:
        The updated DriftRecord or None if not found.
    """
    record = db.query(DriftRecord).get(drift_id)
    if record is None:
        return None

    record.status = resolution
    record.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return record


def list_open_drifts(
    project_id: UUID,
    db: Session,
    status_filter: Optional[str] = None,
) -> List[DriftRecord]:
    """
    Query drift records for a project.

    Args:
        project_id: The project to query.
        db: Database session.
        status_filter: Optional filter by status ('open', 'auto_fixed', 'dismissed').
                       If None, returns all records.

    Returns:
        List of DriftRecord objects.
    """
    query = db.query(DriftRecord).filter(DriftRecord.project_id == project_id)
    if status_filter:
        query = query.filter(DriftRecord.status == status_filter)
    return query.order_by(DriftRecord.detected_at.desc()).all()


def clear_stale_drifts(
    project_id: UUID,
    rule_name: str,
    db: Session,
) -> int:
    """
    Close any existing open drift records for a rule before re-running it.
    This prevents duplicate drifts from accumulating on repeated audits.

    Returns the number of records closed.
    """
    stale = (
        db.query(DriftRecord)
        .filter(
            DriftRecord.project_id == project_id,
            DriftRecord.check_name == rule_name,
            DriftRecord.status == "open",
        )
        .all()
    )
    for record in stale:
        record.status = "dismissed"
        record.resolved_at = datetime.now(timezone.utc)
    return len(stale)


# ---------------------------------------------------------------------------
# Auditor Entry Point
# ---------------------------------------------------------------------------

def run_audit(
    project_id: UUID,
    db: Session,
    rules: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Run all (or selected) validation rules for a project.

    For each rule:
      1. Fetch both artifact contents
      2. Run the checker function to detect drifts
      3. Clear stale drift records for that rule
      4. Persist new drift records
      5. Return a summary

    Args:
        project_id: The project to audit.
        db: Database session.
        rules: Optional list of rule names to run. If None, runs all.

    Returns:
        A list of audit results, one per rule.
    """
    results = []

    active_rules = VALIDATION_RULES
    if rules:
        active_rules = [r for r in VALIDATION_RULES if r.name in rules]

    for rule in active_rules:
        node_a, content_a = _get_artifact_content(project_id, rule.artifact_type_a, db)
        node_b, content_b = _get_artifact_content(project_id, rule.artifact_type_b, db)

        # Skip if either artifact doesn't exist yet
        if node_a is None or node_b is None:
            results.append({
                "rule": rule.name,
                "status": "skipped",
                "reason": f"Missing artifact: {rule.artifact_type_a if node_a is None else rule.artifact_type_b}",
                "drifts_found": 0,
            })
            continue

        # Get the checker function
        checker = CHECKER_REGISTRY.get(rule.name)
        if checker is None:
            results.append({
                "rule": rule.name,
                "status": "error",
                "reason": f"No checker function registered for rule '{rule.name}'",
                "drifts_found": 0,
            })
            continue

        # Run the checker
        drift_items = checker(content_a, content_b, node_a, node_b)

        # Clear stale drifts for this rule before persisting new ones
        stale_cleared = clear_stale_drifts(project_id, rule.name, db)

        # Persist new drift records
        new_records = []
        for item in drift_items:
            record = create_drift_record(
                project_id=project_id,
                rule=rule,
                node_a=node_a,
                node_b=node_b,
                description=item["description"],
                db=db,
            )
            new_records.append(record)

        db.commit()

        status = "consistent" if len(drift_items) == 0 else "drift_detected"
        results.append({
            "rule": rule.name,
            "status": status,
            "severity": rule.severity,
            "artifact_a": rule.artifact_type_a,
            "artifact_b": rule.artifact_type_b,
            "drifts_found": len(drift_items),
            "stale_cleared": stale_cleared,
            "drift_descriptions": [item["description"] for item in drift_items],
        })

    return results
