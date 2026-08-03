"""
Consistency Auditor Agent — Phase 4 (Skeleton)

This module defines the cross-artifact structural validation rules and
the auditor entry point. It will be expanded with the full micro-regeneration
flow in the complete Phase 4 implementation.

Validation Rules (from design.md §6.1):
  1. requirement_coverage:      PRD ↔ SDD
  2. schema_endpoint_mapping:   DB_SCHEMA ↔ API_SPEC
  3. endpoint_requirement_map:  API_SPEC ↔ PRD
  4. story_traceability:        USER_STORIES ↔ PRD
  5. task_coverage:             TASKS ↔ USER_STORIES
"""

from typing import List, Dict, Any, Optional
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


# ---------------------------------------------------------------------------
# Helper: fetch artifact content
# ---------------------------------------------------------------------------

def _get_artifact_content(
    project_id: UUID,
    artifact_type: str,
    db: Session,
) -> tuple[Optional[ArtifactNode], str]:
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


# ---------------------------------------------------------------------------
# Auditor Entry Point (Skeleton)
# ---------------------------------------------------------------------------

def run_audit(
    project_id: UUID,
    db: Session,
    rules: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Run all (or selected) validation rules for a project.

    This is the skeleton — in the full Phase 4 implementation,
    each rule will have a dedicated checker function that parses
    the artifact content and detects specific drift patterns.

    Args:
        project_id: The project to audit.
        db: Database session.
        rules: Optional list of rule names to run. If None, runs all.

    Returns:
        A list of drift detection results.
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
            })
            continue

        # TODO: Phase 4 full implementation will add per-rule checker functions
        # For now, mark as "pending" — the checker logic will be built next
        results.append({
            "rule": rule.name,
            "artifact_a": rule.artifact_type_a,
            "artifact_b": rule.artifact_type_b,
            "status": "pending_implementation",
            "severity": rule.severity,
        })

    return results
