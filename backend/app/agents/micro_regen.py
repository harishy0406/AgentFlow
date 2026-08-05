"""
Micro-Regeneration Engine — Phase 4

Performs targeted, minimal section-level regeneration to fix a specific
cross-artifact drift detected by the Consistency Auditor.

Flow:
1. Load the drift record and identify the owning section
2. Build a targeted prompt with the drift description + both artifact contents
3. Route through the Quality-Signal Router to pick the best model
4. Invoke the LLM with the MICRO_REGEN_PROMPT
5. Update only the corrected section, bump version, log as 'micro_regeneration'
6. Re-run the specific validation rule to verify the fix
"""

import time
from uuid import UUID
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from langchain_core.prompts import PromptTemplate

from ..models import (
    ArtifactNode, ArtifactSection, ArtifactVersion, GenerationLog, DriftRecord
)
from .graph_engine import compute_content_hash
from .router import get_chat_model_for_artifact, RoutingDecision
from .quality_signals import compute_quality_signal
from .prompts import MICRO_REGEN_PROMPT
from .auditor import (
    VALIDATION_RULES, _get_artifact_content, run_audit, resolve_drift_record
)


def _save_version_snapshot(section: ArtifactSection, db: Session) -> None:
    """Persist a snapshot of the section before micro-regeneration."""
    node = db.query(ArtifactNode).get(section.artifact_node_id)
    version = ArtifactVersion(
        artifact_node_id=section.artifact_node_id,
        section_id=section.id,
        version=node.version if node else 1,
        content=section.content,
        content_hash=section.content_hash,
    )
    db.add(version)


def _log_micro_generation(
    project_id: UUID,
    node_id: UUID,
    latency_ms: int,
    decision: RoutingDecision,
    tokens_used: Optional[int],
    db: Session,
) -> None:
    """Log a micro-regeneration event."""
    log = GenerationLog(
        project_id=project_id,
        artifact_node_id=node_id,
        triggered_by="micro_regeneration",
        provider=decision.chosen_provider,
        model=decision.chosen_model,
        tokens_used=tokens_used,
        latency_ms=latency_ms,
    )
    db.add(log)


def _get_rule_by_name(name: str):
    """Look up a ValidationRule by its name."""
    for rule in VALIDATION_RULES:
        return next((r for r in VALIDATION_RULES if r.name == name), None)


def _determine_target_artifact(drift: DriftRecord) -> str:
    """
    Determine which artifact should be fixed for a given drift.
    
    Heuristic: the 'downstream' artifact in the dependency chain is the
    one that should be updated to match the upstream. The design spec's
    dependency order is: PRD → SDD → DB_SCHEMA → API_SPEC, PRD → USER_STORIES → TASKS.
    
    So for a PRD ↔ SDD drift, fix the SDD (downstream).
    """
    UPSTREAM_PRIORITY = {
        "PRD": 0,
        "SDD": 1,
        "DB_SCHEMA": 2,
        "API_SPEC": 3,
        "USER_STORIES": 4,
        "TASKS": 5,
    }
    node_a_type = None
    node_b_type = None

    # We stored artifact_a and artifact_b as relationships
    # but we need their types — use the drift's check_name to look up
    rule = _get_rule_by_name(drift.check_name)
    if rule:
        prio_a = UPSTREAM_PRIORITY.get(rule.artifact_type_a, 99)
        prio_b = UPSTREAM_PRIORITY.get(rule.artifact_type_b, 99)
        # Fix the downstream one (higher priority number)
        if prio_a >= prio_b:
            return rule.artifact_type_a
        else:
            return rule.artifact_type_b

    # Fallback: fix artifact_b
    return "SDD"


def fix_drift(
    drift_id: UUID,
    db: Session,
) -> Dict[str, Any]:
    """
    Auto-fix a specific drift record via micro-regeneration.

    1. Load the drift record
    2. Determine which artifact/section to fix
    3. Build the micro-regen prompt with both artifact contents
    4. Route to the best model
    5. Invoke the LLM
    6. Update the section, bump version, log event
    7. Re-run the validation rule to verify
    8. Mark the drift as auto_fixed (or leave open if re-check fails)

    Returns a result dict with fix details.
    """
    drift = db.query(DriftRecord).get(drift_id)
    if drift is None:
        raise ValueError(f"Drift record {drift_id} not found")

    if drift.status != "open":
        return {
            "drift_id": str(drift_id),
            "status": "already_resolved",
            "message": f"Drift is already '{drift.status}'",
        }

    # Look up the rule
    rule = _get_rule_by_name(drift.check_name)
    if rule is None:
        raise ValueError(f"Unknown check '{drift.check_name}'")

    # Fetch both artifact contents
    node_a, content_a = _get_artifact_content(drift.project_id, rule.artifact_type_a, db)
    node_b, content_b = _get_artifact_content(drift.project_id, rule.artifact_type_b, db)

    if node_a is None or node_b is None:
        raise ValueError("One of the drift artifacts no longer exists")

    # Determine which artifact to fix
    target_type = _determine_target_artifact(drift)
    target_node = node_a if rule.artifact_type_a == target_type else node_b
    target_content = content_a if rule.artifact_type_a == target_type else content_b

    # Get the first section of the target artifact (simplification:
    # in a full impl, we'd identify the exact section from drift.section_a_id/section_b_id)
    target_sections = (
        db.query(ArtifactSection)
        .filter(ArtifactSection.artifact_node_id == target_node.id)
        .order_by(ArtifactSection.section_key)
        .all()
    )
    if not target_sections:
        raise ValueError(f"Target artifact '{target_type}' has no sections")

    # Use the specific section if available, otherwise the first section
    if drift.section_a_id or drift.section_b_id:
        target_section_id = drift.section_a_id if rule.artifact_type_a == target_type else drift.section_b_id
        target_section = db.query(ArtifactSection).get(target_section_id) if target_section_id else target_sections[0]
        if target_section is None:
            target_section = target_sections[0]
    else:
        target_section = target_sections[0]

    # Snapshot before overwrite
    _save_version_snapshot(target_section, db)

    # Build prompt context
    ctx = {
        "drift_description": drift.description,
        "rule_name": rule.name,
        "rule_description": rule.description,
        "artifact_type_a": rule.artifact_type_a,
        "content_a": content_a,
        "artifact_type_b": rule.artifact_type_b,
        "content_b": content_b,
        "target_artifact_type": target_type,
        "section_content": target_section.content,
    }

    # Route to the best model
    context_size = sum(len(v) for v in ctx.values()) // 4
    llm, decision = get_chat_model_for_artifact(target_type, context_size, db)

    # Invoke LLM
    prompt = PromptTemplate.from_template(MICRO_REGEN_PROMPT)
    chain = prompt | llm

    start_ms = int(time.time() * 1000)
    response = chain.invoke(ctx)
    end_ms = int(time.time() * 1000)

    # Update section
    new_content = response.content
    target_section.content = new_content
    target_section.content_hash = compute_content_hash(new_content)
    target_section.updated_at = datetime.now(timezone.utc)

    # Compute quality signal
    quality_score = compute_quality_signal(
        target_type, new_content, drift.project_id, db
    )
    target_node.quality_signal_score = quality_score
    target_node.generated_by_model = f"{decision.chosen_provider}/{decision.chosen_model}"
    target_node.version += 1
    target_node.status = "fresh"

    # Extract token usage
    tokens_used = None
    if hasattr(response, 'response_metadata'):
        usage = response.response_metadata.get('token_usage', {})
        if usage:
            tokens_used = usage.get('total_tokens')

    # Log the micro-regeneration
    _log_micro_generation(
        drift.project_id, target_node.id, end_ms - start_ms,
        decision, tokens_used, db,
    )

    db.commit()

    # Re-run the specific validation rule to verify the fix
    verify_results = run_audit(drift.project_id, db, rules=[drift.check_name])
    fix_verified = False
    if verify_results:
        result = verify_results[0]
        if result.get("status") == "consistent" or result.get("drifts_found", 1) == 0:
            fix_verified = True

    # Mark drift as fixed if verified
    if fix_verified:
        resolve_drift_record(drift_id, "auto_fixed", db)
        status = "fixed"
    else:
        status = "fix_attempted_but_unresolved"

    return {
        "drift_id": str(drift_id),
        "status": status,
        "target_artifact": target_type,
        "target_section_id": str(target_section.id),
        "fix_verified": fix_verified,
        "latency_ms": end_ms - start_ms,
        "model_used": f"{decision.chosen_provider}/{decision.chosen_model}",
        "routing_decision": decision.to_dict(),
    }
