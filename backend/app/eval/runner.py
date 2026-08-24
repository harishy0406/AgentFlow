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
from .corpus import EVAL_CORPUS
from .baselines import evaluate_single_llm, evaluate_multi_agent_no_graph, evaluate_agentflow

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
    Run evaluation across the test corpus with benchmark metrics calculated
    specifically for the requested baseline_type configuration.
    """
    eval_run = EvalRun(run_name=run_name, baseline_type=baseline_type)
    db.add(eval_run)
    db.commit()

    total_cost = 0.0
    total_latency = 0
    total_drifts = 0
    quality_scores = []

    for item in EVAL_CORPUS[:limit]:
        project = create_eval_project(item, db)
        
        if baseline_type == "single-llm":
            metrics = evaluate_single_llm(item["brief"])
        elif baseline_type == "multi-agent-no-graph":
            metrics = evaluate_multi_agent_no_graph(item["brief"], edit_scenario=False)
        else: # agentflow
            metrics = evaluate_agentflow(item["brief"], edit_scenario=False)

        # Record evaluation result
        result = EvalResult(
            eval_run_id=eval_run.id,
            project_id=project.id,
            scenario_type=metrics.scenario,
            cost_usd=metrics.cost_usd,
            latency_ms=metrics.latency_ms,
            quality_score=metrics.quality_score,
            drifts_detected=metrics.drifts_detected
        )
        db.add(result)
        db.commit()

        total_latency += metrics.latency_ms
        total_drifts += metrics.drifts_detected
        quality_scores.append(metrics.quality_score)
        total_cost += metrics.cost_usd

    # Update run summary
    eval_run.total_cost_usd = round(total_cost, 4)
    eval_run.total_latency_ms = total_latency
    eval_run.total_drifts = total_drifts
    if quality_scores:
        eval_run.avg_quality_score = round(sum(quality_scores) / len(quality_scores), 3)
    
    db.commit()
    return eval_run

