from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID
from typing import List, Optional

from . import models, schemas
from .database import engine, get_db
from .agents.graph_engine import ARTIFACT_DEPENDENCY_MAP, TOPOLOGICAL_ORDER
from .agents.orchestrator import handle_section_edit, rollback_section
from .agents.provider_registry import PROVIDER_REGISTRY
from .agents.router import route as route_model
from .agents.auditor import run_audit, list_open_drifts, resolve_drift_record
from .agents.micro_regen import fix_drift

# Create database tables (in a real app, use alembic)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AgentFlow API", version="0.4.0")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/")
def read_root():
    return {"status": "ok", "message": "AgentFlow API is running"}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@app.post("/projects/", response_model=schemas.Project)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    db_project = models.Project(name=project.name, brief=project.brief)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    # In a full implementation, we would trigger the initial LangGraph generation here
    return db_project


@app.get("/projects/{project_id}", response_model=schemas.Project)
def read_project(project_id: UUID, db: Session = Depends(get_db)):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return db_project


# ---------------------------------------------------------------------------
# Phase 2: Dependency Graph View
# ---------------------------------------------------------------------------

@app.get("/projects/{project_id}/graph", response_model=schemas.DependencyGraphOut)
def get_project_graph(project_id: UUID, db: Session = Depends(get_db)):
    """Return the typed dependency graph for a project, with node statuses."""
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    nodes_out = []
    for node in db_project.artifact_nodes:
        section_count = (
            db.query(models.ArtifactSection)
            .filter(models.ArtifactSection.artifact_node_id == node.id)
            .count()
        )
        nodes_out.append(schemas.GraphNodeOut(
            id=node.id,
            artifact_type=node.artifact_type,
            version=node.version,
            status=node.status,
            section_count=section_count,
        ))

    edges_out = []
    for child_type, parent_types in ARTIFACT_DEPENDENCY_MAP.items():
        for parent_type in parent_types:
            edges_out.append(schemas.GraphEdgeOut(
                from_artifact_type=parent_type,
                to_artifact_type=child_type,
            ))

    return schemas.DependencyGraphOut(nodes=nodes_out, edges=edges_out)


# ---------------------------------------------------------------------------
# Phase 2: Get Artifact by Type
# ---------------------------------------------------------------------------

@app.get("/projects/{project_id}/artifacts/{artifact_type}", response_model=schemas.ArtifactNode)
def get_artifact(project_id: UUID, artifact_type: str, db: Session = Depends(get_db)):
    """Fetch a specific artifact node with all its sections."""
    node = (
        db.query(models.ArtifactNode)
        .filter(
            models.ArtifactNode.project_id == project_id,
            models.ArtifactNode.artifact_type == artifact_type,
        )
        .first()
    )
    if node is None:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_type} not found")
    return node


# ---------------------------------------------------------------------------
# Phase 2: Edit a Section → Selective Regeneration
# ---------------------------------------------------------------------------

@app.patch(
    "/projects/{project_id}/artifacts/{artifact_type}/sections/{section_id}",
    response_model=schemas.RegenerationResult,
)
def edit_section(
    project_id: UUID,
    artifact_type: str,
    section_id: UUID,
    body: schemas.ArtifactSectionUpdate,
    db: Session = Depends(get_db),
):
    """
    Edit a section's content. This triggers the Phase 2 diff-aware selective
    regeneration: the system computes the diff, finds all downstream dirty
    sections via BFS, and regenerates only those sections in topological
    order.
    """
    # Validate the section exists and belongs to the right artifact/project
    section = db.query(models.ArtifactSection).get(section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")

    node = db.query(models.ArtifactNode).get(section.artifact_node_id)
    if node is None or str(node.project_id) != str(project_id) or node.artifact_type != artifact_type:
        raise HTTPException(status_code=404, detail="Section does not belong to the specified artifact/project")

    result = handle_section_edit(section_id, body.content, db)
    return schemas.RegenerationResult(**result)


# ---------------------------------------------------------------------------
# Phase 2: Version History & Rollback
# ---------------------------------------------------------------------------

@app.get(
    "/projects/{project_id}/artifacts/{artifact_type}/sections/{section_id}/versions",
    response_model=List[schemas.ArtifactVersionOut],
)
def list_section_versions(
    project_id: UUID,
    artifact_type: str,
    section_id: UUID,
    db: Session = Depends(get_db),
):
    """List all prior version snapshots for a given section."""
    versions = (
        db.query(models.ArtifactVersion)
        .filter(models.ArtifactVersion.section_id == section_id)
        .order_by(models.ArtifactVersion.version.desc())
        .all()
    )
    return versions


@app.post(
    "/projects/{project_id}/artifacts/{artifact_type}/sections/{section_id}/rollback",
    response_model=schemas.RollbackResponse,
)
def rollback_section_endpoint(
    project_id: UUID,
    artifact_type: str,
    section_id: UUID,
    body: schemas.RollbackRequest,
    db: Session = Depends(get_db),
):
    """
    Rollback a section to a specific prior version. The current content
    is snapshot-ed before being overwritten, and the node version is bumped.
    """
    try:
        result = rollback_section(section_id, body.target_version, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return schemas.RollbackResponse(**result)


# ---------------------------------------------------------------------------
# Phase 2: Manual Regeneration Trigger
# ---------------------------------------------------------------------------

@app.post(
    "/projects/{project_id}/regenerate/{artifact_type}",
    response_model=schemas.RegenerationResult,
)
def trigger_regeneration(
    project_id: UUID,
    artifact_type: str,
    db: Session = Depends(get_db),
):
    """
    Manually trigger regeneration of a specific artifact type.
    This treats every section of the artifact as dirty and regenerates
    them using the selective regeneration flow.
    """
    node = (
        db.query(models.ArtifactNode)
        .filter(
            models.ArtifactNode.project_id == project_id,
            models.ArtifactNode.artifact_type == artifact_type,
        )
        .first()
    )
    if node is None:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_type} not found")

    # Find the upstream sections that feed into this artifact and trigger
    # regeneration from each one. For simplicity we regenerate by treating
    # the first upstream section as the edit origin.
    sections = (
        db.query(models.ArtifactSection)
        .filter(models.ArtifactSection.artifact_node_id == node.id)
        .all()
    )
    if not sections:
        raise HTTPException(status_code=400, detail="Artifact has no sections to regenerate")

    # Use the first section's traces_to to find the upstream edit point
    # If no traces, just re-run from the section itself
    combined_result = {
        "edited_section_id": str(sections[0].id),
        "content_changed": True,
        "dirty_sections": [],
        "regenerated_artifacts": [],
    }

    for sec in sections:
        result = handle_section_edit(sec.id, sec.content, db)
        combined_result["dirty_sections"].extend(result.get("dirty_sections", []))
        for art in result.get("regenerated_artifacts", []):
            if art not in combined_result["regenerated_artifacts"]:
                combined_result["regenerated_artifacts"].append(art)

    return schemas.RegenerationResult(**combined_result)


# ---------------------------------------------------------------------------
# Phase 3: Metrics
# ---------------------------------------------------------------------------

@app.get("/projects/{project_id}/metrics", response_model=schemas.ProjectMetrics)
def get_project_metrics(project_id: UUID, db: Session = Depends(get_db)):
    """
    Return cost, latency, quality-signal metrics per artifact type
    for the project.
    """
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Aggregate generation logs
    total_cost = (
        db.query(func.sum(models.GenerationLog.cost_usd))
        .filter(models.GenerationLog.project_id == project_id)
        .scalar()
    )
    total_gens = (
        db.query(func.count(models.GenerationLog.id))
        .filter(models.GenerationLog.project_id == project_id)
        .scalar()
    )

    artifact_metrics = []
    for art_type in TOPOLOGICAL_ORDER:
        node = (
            db.query(models.ArtifactNode)
            .filter(
                models.ArtifactNode.project_id == project_id,
                models.ArtifactNode.artifact_type == art_type,
            )
            .first()
        )
        if node is None:
            continue

        gen_count = (
            db.query(func.count(models.GenerationLog.id))
            .filter(models.GenerationLog.artifact_node_id == node.id)
            .scalar()
        )
        avg_latency = (
            db.query(func.avg(models.GenerationLog.latency_ms))
            .filter(models.GenerationLog.artifact_node_id == node.id)
            .scalar()
        )
        total_art_cost = (
            db.query(func.sum(models.GenerationLog.cost_usd))
            .filter(models.GenerationLog.artifact_node_id == node.id)
            .scalar()
        )

        artifact_metrics.append(schemas.ArtifactMetrics(
            artifact_type=art_type,
            avg_quality_signal=node.quality_signal_score,
            total_generations=gen_count or 0,
            total_cost_usd=float(total_art_cost) if total_art_cost else None,
            avg_latency_ms=float(avg_latency) if avg_latency else None,
            last_model_used=node.generated_by_model,
        ))

    return schemas.ProjectMetrics(
        project_id=project_id,
        total_cost_usd=float(total_cost) if total_cost else None,
        total_generations=total_gens or 0,
        artifact_metrics=artifact_metrics,
    )


# ---------------------------------------------------------------------------
# Phase 3: Provider Registry
# ---------------------------------------------------------------------------

@app.get("/providers", response_model=List[schemas.ProviderOut])
def list_providers():
    """List all registered LLM providers and their models."""
    result = []
    for provider in PROVIDER_REGISTRY.all_providers():
        models_out = [
            schemas.ProviderModelOut(
                provider=m.provider,
                model_name=m.model_name,
                cost_per_input_token=m.cost_per_input_token,
                cost_per_output_token=m.cost_per_output_token,
                max_context_tokens=m.max_context_tokens,
            )
            for m in provider.models
        ]
        result.append(schemas.ProviderOut(
            name=provider.name,
            is_available=provider.is_available(),
            models=models_out,
        ))
    return result


@app.get("/routing/preview/{artifact_type}", response_model=schemas.RoutingDecisionOut)
def preview_routing(
    artifact_type: str,
    context_size: int = 1000,
    db: Session = Depends(get_db),
):
    """
    Preview what model the router would select for a given artifact type
    without actually running a generation.
    """
    decision = route_model(artifact_type, context_size, db)
    return schemas.RoutingDecisionOut(**decision.to_dict())


# ---------------------------------------------------------------------------
# Phase 4: Consistency Auditor
# ---------------------------------------------------------------------------

@app.post("/projects/{project_id}/audit", response_model=schemas.AuditResult)
def trigger_audit(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Run the full Consistency Auditor on a project. Checks all 5 cross-artifact
    validation rules and persists any detected drifts.
    """
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    results = run_audit(project_id, db)

    rule_results = [schemas.AuditRuleResult(**r) for r in results]
    total_drifts = sum(r.get("drifts_found", 0) for r in results)

    return schemas.AuditResult(
        project_id=project_id,
        total_rules_checked=len(results),
        total_drifts_found=total_drifts,
        rules=rule_results,
    )


@app.get("/projects/{project_id}/drifts", response_model=List[schemas.DriftRecordOut])
def get_project_drifts(
    project_id: UUID,
    status: Optional[str] = Query(None, description="Filter by status: open, auto_fixed, dismissed"),
    db: Session = Depends(get_db),
):
    """List all drift records for a project, optionally filtered by status."""
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    drifts = list_open_drifts(project_id, db, status_filter=status)
    return drifts


@app.post(
    "/projects/{project_id}/drifts/{drift_id}/fix",
    response_model=schemas.DriftFixResult,
)
def auto_fix_drift(
    project_id: UUID,
    drift_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Trigger micro-regeneration to auto-fix a specific drift.
    The system will regenerate the minimum section needed, then re-run
    the validation rule to verify the fix.
    """
    try:
        result = fix_drift(drift_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return schemas.DriftFixResult(**result)


@app.post(
    "/projects/{project_id}/drifts/{drift_id}/dismiss",
    response_model=schemas.DriftRecordOut,
)
def dismiss_drift(
    project_id: UUID,
    drift_id: UUID,
    db: Session = Depends(get_db),
):
    """Dismiss a drift record (human override — marking it as not needing a fix)."""
    record = resolve_drift_record(drift_id, "dismissed", db)
    if record is None:
        raise HTTPException(status_code=404, detail="Drift record not found")
    return record


# ---------------------------------------------------------------------------
# Phase 6: Evaluation API
# ---------------------------------------------------------------------------

from .eval.runner import run_evaluation_batch

@app.post("/eval/run", response_model=schemas.EvalRunOut)
def trigger_eval_run(
    run_name: str,
    baseline_type: str,
    limit: int = 5,
    db: Session = Depends(get_db)
):
    """Trigger an evaluation run against the test corpus."""
    try:
        run = run_evaluation_batch(run_name, baseline_type, db, limit)
        return run
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/eval/runs", response_model=List[schemas.EvalRunOut])
def list_eval_runs(db: Session = Depends(get_db)):
    """List all evaluation runs and their results."""
    return db.query(models.EvalRun).order_by(models.EvalRun.completed_at.desc()).all()


