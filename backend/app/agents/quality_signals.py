"""
Quality Signal Engine — Phase 3

Computes artifact-type-specific structural quality signals after generation.
These signals are used by the router to learn which models produce the best
results for each artifact type, and are logged for observability.

Quality signals per artifact type (from design.md §5.1):
  - PRD:          Requirement-traceability coverage
  - SDD:          Component-coverage completeness
  - DB_SCHEMA:    Referential integrity score
  - API_SPEC:     Endpoint/method contract completeness
  - USER_STORIES: Requirement traceability
  - TASKS:        Story coverage
"""

import re
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ..models import ArtifactNode, ArtifactSection


# ---------------------------------------------------------------------------
# Individual signal computers
# ---------------------------------------------------------------------------

def _compute_prd_signal(content: str) -> float:
    """
    Requirement-traceability coverage.
    Heuristic: count the number of clearly stated requirements
    (lines starting with FR-, NFR-, or containing "shall") and check
    what fraction are well-formed (have a requirement ID pattern).
    """
    lines = content.splitlines()
    total_requirement_lines = 0
    well_formed = 0

    for line in lines:
        stripped = line.strip()
        # Detect requirement-like lines
        if any(kw in stripped.lower() for kw in ["shall", "must", "requirement"]):
            total_requirement_lines += 1
            # Well-formed if it has an ID pattern like FR-1, NFR-2, REQ-01
            if re.search(r"\b(FR|NFR|REQ|US)-?\d+", stripped, re.IGNORECASE):
                well_formed += 1

    if total_requirement_lines == 0:
        return 0.5  # No requirements detected — neutral score
    return well_formed / total_requirement_lines


def _compute_sdd_signal(content: str, prd_content: str) -> float:
    """
    Component-coverage completeness.
    Heuristic: extract requirement IDs from the PRD, then check what
    fraction are referenced somewhere in the SDD.
    """
    # Extract requirement IDs from PRD
    req_ids = set(re.findall(r"\b(FR|NFR|REQ|US)-?\d+", prd_content, re.IGNORECASE))
    if not req_ids:
        return 0.5

    # Count how many are mentioned in SDD
    covered = sum(1 for rid in req_ids if rid.lower() in content.lower())
    return covered / len(req_ids)


def _compute_db_schema_signal(content: str) -> float:
    """
    Referential integrity score.
    Heuristic: count FOREIGN KEY declarations and check that each
    REFERENCES target is also defined as a CREATE TABLE in the content.
    """
    # Find all table names
    tables = set(
        m.group(1).lower()
        for m in re.finditer(r"CREATE\s+TABLE\s+(\w+)", content, re.IGNORECASE)
    )
    if not tables:
        return 0.5  # Not a SQL-formatted schema — neutral

    # Find all REFERENCES targets
    fk_targets = [
        m.group(1).lower()
        for m in re.finditer(r"REFERENCES\s+(\w+)", content, re.IGNORECASE)
    ]
    if not fk_targets:
        # No FKs — might be fine for small schemas
        return 0.7

    resolved = sum(1 for t in fk_targets if t in tables)
    return resolved / len(fk_targets)


def _compute_api_spec_signal(content: str, db_content: str) -> float:
    """
    Endpoint/method contract completeness.
    Heuristic: count endpoint definitions (GET/POST/PATCH/DELETE/PUT
    followed by a path), then check how many have a response/request
    body specified nearby.
    """
    endpoint_pattern = re.compile(
        r"\b(GET|POST|PUT|PATCH|DELETE)\b\s+[/`]", re.IGNORECASE
    )
    endpoints = endpoint_pattern.findall(content)
    total = len(endpoints)
    if total == 0:
        return 0.5

    # Check for response/request schema keywords near endpoints
    schema_keywords = ["request", "response", "body", "schema", "payload", "parameters"]
    lines = content.lower().splitlines()
    documented = 0
    for i, line in enumerate(lines):
        if endpoint_pattern.search(line):
            # Look in a window of ±10 lines for schema documentation
            window = "\n".join(lines[max(0, i - 5): i + 10])
            if any(kw in window for kw in schema_keywords):
                documented += 1

    return documented / total if total > 0 else 0.5


def _compute_user_stories_signal(content: str, prd_content: str) -> float:
    """
    Requirement traceability.
    Heuristic: count user stories (lines containing "As a"), then
    check how many reference a requirement ID from the PRD.
    """
    req_ids = set(re.findall(r"\b(FR|NFR|REQ|US)-?\d+", prd_content, re.IGNORECASE))
    story_lines = [
        line for line in content.splitlines()
        if "as a" in line.lower() or "i want" in line.lower()
    ]
    total = len(story_lines)
    if total == 0:
        return 0.5

    if not req_ids:
        # No requirement IDs in PRD to trace against
        return 0.5

    traced = 0
    for line in story_lines:
        if any(rid.lower() in line.lower() for rid in req_ids):
            traced += 1
    return traced / total


def _compute_tasks_signal(content: str, stories_content: str) -> float:
    """
    Story coverage.
    Heuristic: extract user story identifiers or "As a" counts from
    stories_content, then check how many are referenced in the task
    breakdown.
    """
    story_lines = [
        line.strip() for line in stories_content.splitlines()
        if "as a" in line.lower() or "i want" in line.lower()
    ]
    total_stories = len(story_lines)
    if total_stories == 0:
        return 0.5

    # Check for task items (lines with checkbox or numbered items)
    task_lines = [
        line for line in content.splitlines()
        if re.match(r"\s*[-*\d.]", line.strip())
    ]
    total_tasks = len(task_lines)

    if total_tasks == 0:
        return 0.0

    # Simple ratio: at least 1 task per story is baseline coverage
    coverage = min(total_tasks / total_stories, 1.0)
    return coverage


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_quality_signal(
    artifact_type: str,
    content: str,
    project_id: UUID,
    db: Session,
) -> float:
    """
    Compute the structural quality signal for a generated artifact.

    Returns a float between 0.0 and 1.0.
    """
    if artifact_type == "PRD":
        return _compute_prd_signal(content)

    elif artifact_type == "SDD":
        prd = _get_artifact_content(project_id, "PRD", db)
        return _compute_sdd_signal(content, prd)

    elif artifact_type == "DB_SCHEMA":
        return _compute_db_schema_signal(content)

    elif artifact_type == "API_SPEC":
        db_content = _get_artifact_content(project_id, "DB_SCHEMA", db)
        return _compute_api_spec_signal(content, db_content)

    elif artifact_type == "USER_STORIES":
        prd = _get_artifact_content(project_id, "PRD", db)
        return _compute_user_stories_signal(content, prd)

    elif artifact_type == "TASKS":
        stories = _get_artifact_content(project_id, "USER_STORIES", db)
        return _compute_tasks_signal(content, stories)

    return 0.5  # Unknown artifact type


def _get_artifact_content(project_id: UUID, artifact_type: str, db: Session) -> str:
    """Helper to concatenate all sections of an artifact."""
    node = (
        db.query(ArtifactNode)
        .filter(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type,
        )
        .first()
    )
    if node is None:
        return ""
    sections = (
        db.query(ArtifactSection)
        .filter(ArtifactSection.artifact_node_id == node.id)
        .order_by(ArtifactSection.section_key)
        .all()
    )
    return "\n\n".join(s.content for s in sections)
