"""
Phase 6: Evaluation Runner

Automates the execution of the AgentFlow pipeline against the test corpus
under different configurations (baselines vs. AgentFlow).
"""

import time
from uuid import UUID
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from ..models import Project, EvalRun, EvalResult
from ..agents.graph import run_pipeline
from ..agents.orchestrator import handle_section_edit
from ..agents.auditor import run_audit
from .corpus import EVAL_CORPUS

def create_eval_project(corpus_item: Dict[str, str], db: Session) -> Project:
    project = Project(name=f"[EVAL] {corpus_item['name']}", brief=corpus_item['brief'])
    db.add(project)
    db.commit()
    return project

def run_evaluation_batch(
    run_name: str,
    baseline_type: str, # 'single-llm', 'multi-agent-no-graph', 'agentflow'
    db: Session,
    limit: int = 5
) -> EvalRun:
    """
    Run the evaluation across the corpus. 
    (In a real scenario, this would use different router overrides based on baseline_type).
    """
    eval_run = EvalRun(run_name=run_name, baseline_type=baseline_type)
    db.add(eval_run)
    db.commit()

    total_cost = 0.0
    total_latency = 0
    total_drifts = 0
    quality_scores = []

    for item in EVAL_CORPUS[:limit]:
        # 1. Full Generation Scenario
        project = create_eval_project(item, db)
        start_ms = int(time.time() * 1000)
        
        # Run full pipeline
        # Note: To truly test 'single-llm' vs 'agentflow', we would pass 
        # a configuration flag to run_pipeline. For this skeleton, we just call it.
        run_pipeline(project.id, db)
        
        end_ms = int(time.time() * 1000)
        latency = end_ms - start_ms
        
        # Run audit to check for drifts
        audit_results = run_audit(project.id, db)
        drifts = sum(r.get("drifts_found", 0) for r in audit_results)
        
        # Record result
        result = EvalResult(
            eval_run_id=eval_run.id,
            project_id=project.id,
            scenario_type="full_generation",
            cost_usd=0.05, # Mock cost
            latency_ms=latency,
            quality_score=0.85, # Mock quality
            drifts_detected=drifts
        )
        db.add(result)
        db.commit()

        total_latency += latency
        total_drifts += drifts
        quality_scores.append(0.85)
        total_cost += 0.05

    # Update run summary
    eval_run.total_cost_usd = total_cost
    eval_run.total_latency_ms = total_latency
    eval_run.total_drifts = total_drifts
    if quality_scores:
        eval_run.avg_quality_score = sum(quality_scores) / len(quality_scores)
    
    db.commit()
    return eval_run
