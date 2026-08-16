"""
Phase 6: Automated Edit Simulator

Simulates mid-project edits (e.g., altering a PRD requirement) 
to benchmark the selective regeneration performance (cost/latency) 
vs. a full re-generation baseline.
"""

import time
from sqlalchemy.orm import Session
from uuid import UUID

from ..models import ArtifactSection, EvalResult
from ..agents.orchestrator import handle_section_edit
from ..agents.auditor import run_audit

def simulate_mid_project_edit(
    project_id: UUID,
    eval_run_id: UUID,
    db: Session
) -> EvalResult:
    """
    Simulates a user editing the first section of the PRD.
    Measures the latency, cost, and downstream artifacts regenerated.
    """
    
    # 1. Find a PRD section to 'edit'
    prd_section = (
        db.query(ArtifactSection)
        .join(ArtifactSection.node)
        .filter(ArtifactSection.node.has(project_id=project_id, artifact_type="PRD"))
        .first()
    )
    
    if not prd_section:
        raise ValueError("No PRD section found to simulate edit.")

    # 2. Append mock edit
    new_content = prd_section.content + "\n\n[EDIT]: Must include multi-factor authentication (MFA) via SMS."

    start_ms = int(time.time() * 1000)
    
    # 3. Trigger orchestrator edit handling (Selective Regeneration)
    edit_summary = handle_section_edit(prd_section.id, new_content, db)
    
    end_ms = int(time.time() * 1000)
    latency = end_ms - start_ms

    # 4. Run audit
    audit_results = run_audit(project_id, db)
    drifts = sum(r.get("drifts_found", 0) for r in audit_results)
    
    # Note: In a full implementation, edit_summary would return actual cost.
    # For now, we mock the cost based on number of regenerated artifacts.
    cost_usd = len(edit_summary.get("regenerated_artifacts", [])) * 0.01

    # 5. Record result
    result = EvalResult(
        eval_run_id=eval_run_id,
        project_id=project_id,
        scenario_type="mid_project_edit",
        cost_usd=cost_usd,
        latency_ms=latency,
        quality_score=0.90, # Mock retention quality
        drifts_detected=drifts
    )
    
    db.add(result)
    db.commit()
    
    return result
