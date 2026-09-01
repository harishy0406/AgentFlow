from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID
from typing import List, Optional
from datetime import datetime, timezone
import json
import io
import zipfile
import os
import hashlib
import shutil
from pathlib import Path

from . import models, schemas
from .database import engine, get_db
from .agents.graph_engine import ARTIFACT_DEPENDENCY_MAP, TOPOLOGICAL_ORDER
from .agents.orchestrator import handle_section_edit, rollback_section
from .agents.provider_registry import PROVIDER_REGISTRY
from .agents.router import route as route_model
from .agents.auditor import run_audit, list_open_drifts, resolve_drift_record
from .agents.micro_regen import fix_drift
from .agents.scaffolder import parse_code_files, sanitize_project_slug
from .agents.tester import verify_project_codebase
from .agents.assistant import answer_project_query
from .agents.migrator import generate_and_save_migrations
from .agents.workspace import validate_workspace_cross_service_contracts
from .agents.openapi_generator import generate_openapi_spec

# Create database tables (in a real app, use alembic)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AgentFlow API", version="0.6.0")


# ---------------------------------------------------------------------------
# WebSocket Connection Manager (Phase 5: Real-time Updates)
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Manages active WebSocket connections per project for real-time status broadcasts."""

    def __init__(self):
        # { project_id_str: [websocket1, websocket2, ...] }
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, project_id: str, websocket: WebSocket):
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)

    def disconnect(self, project_id: str, websocket: WebSocket):
        if project_id in self.active_connections:
            self.active_connections[project_id].remove(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]

    async def broadcast(self, project_id: str, message: dict):
        """Send a JSON message to all clients watching a given project."""
        if project_id in self.active_connections:
            payload = json.dumps(message)
            for connection in self.active_connections[project_id]:
                try:
                    await connection.send_text(payload)
                except Exception:
                    pass  # Client may have disconnected


ws_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/")
def read_root():
    return {"status": "ok", "message": "AgentFlow API is running"}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

from .agents.provider_registry import generate_text
from .agents.prompts import CLARIFICATION_PROMPT

@app.post("/projects/clarify")
def clarify_project(req: schemas.ClarifyRequest):
    """Phase 1: HITL step. Returns clarifying questions for a project brief."""
    prompt = CLARIFICATION_PROMPT.format(project_brief=req.brief)
    # Using the default model for clarification
    questions_text = generate_text(prompt, "claude-3-haiku") 
    return {"questions": questions_text}


from .agents.graph import run_pipeline

@app.post("/projects/", response_model=schemas.Project)
@app.post("/projects", response_model=schemas.Project)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    db_project = models.Project(
        name=project.name, 
        brief=project.brief,
        clarifications=project.clarifications
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


@app.post("/workspaces", response_model=schemas.WorkspaceOut)
@app.post("/workspaces/", response_model=schemas.WorkspaceOut)
def create_workspace(payload: schemas.WorkspaceCreate, db: Session = Depends(get_db)):
    """Creates a multi-project workspace for orchestrating microservices or distributed platforms."""
    ws = models.Workspace(name=payload.name, description=payload.description)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return schemas.WorkspaceOut(
        id=ws.id,
        name=ws.name,
        description=ws.description,
        created_at=ws.created_at,
        projects_count=len(ws.projects),
        projects=ws.projects
    )


@app.get("/workspaces", response_model=List[schemas.WorkspaceOut])
@app.get("/workspaces/", response_model=List[schemas.WorkspaceOut])
def list_workspaces(db: Session = Depends(get_db)):
    """Lists all active workspaces with project counts."""
    workspaces = db.query(models.Workspace).order_by(models.Workspace.created_at.desc()).all()
    return [
        schemas.WorkspaceOut(
            id=w.id,
            name=w.name,
            description=w.description,
            created_at=w.created_at,
            projects_count=len(w.projects),
            projects=w.projects
        )
        for w in workspaces
    ]


@app.get("/workspaces/{workspace_id}", response_model=schemas.WorkspaceOut)
def get_workspace(workspace_id: UUID, db: Session = Depends(get_db)):
    """Fetches details and assigned projects for a workspace."""
    ws = db.query(models.Workspace).filter(models.Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return schemas.WorkspaceOut(
        id=ws.id,
        name=ws.name,
        description=ws.description,
        created_at=ws.created_at,
        projects_count=len(ws.projects),
        projects=ws.projects
    )


@app.post("/workspaces/{workspace_id}/projects/{project_id}", response_model=schemas.WorkspaceOut)
def assign_project_to_workspace(workspace_id: UUID, project_id: UUID, db: Session = Depends(get_db)):
    """Assigns an autonomous project/service to a multi-project workspace."""
    ws = db.query(models.Workspace).filter(models.Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.workspace_id = ws.id
    db.commit()
    db.refresh(ws)
    return schemas.WorkspaceOut(
        id=ws.id,
        name=ws.name,
        description=ws.description,
        created_at=ws.created_at,
        projects_count=len(ws.projects),
        projects=ws.projects
    )


@app.post("/workspaces/{workspace_id}/validate-contracts", response_model=schemas.WorkspaceContractsOut)
def validate_workspace_contracts(workspace_id: UUID, db: Session = Depends(get_db)):
    """
    Validates cross-service API contracts and schema dependencies across
    all microservices/projects in the workspace.
    """
    try:
        res = validate_workspace_cross_service_contracts(workspace_id, db)
        return schemas.WorkspaceContractsOut(**res)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/projects", response_model=List[schemas.Project])
@app.get("/projects/", response_model=List[schemas.Project])
def list_projects(db: Session = Depends(get_db)):
    """List all projects in descending order of creation."""
    return db.query(models.Project).order_by(models.Project.created_at.desc()).all()


@app.get("/templates", response_model=List[schemas.ProjectTemplateOut])
def list_project_templates():
    """Returns curated starter project templates with pre-configured briefs and sample requirements."""
    return [
        schemas.ProjectTemplateOut(
            id="saas_ai_reviewer",
            title="AI-Powered Code Reviewer",
            category="DevOps & AI Tools",
            description="Automated pull request analysis bot with AST static scanning, security vulnerability checks, and GitHub webhook integration.",
            suggested_brief="Build an enterprise AI Code Reviewer that automatically parses GitHub pull requests, performs static AST analysis, checks for OWASP vulnerabilities, and posts inline suggestions with benchmarked test cases.",
            sample_clarifications={
                "Supported VCS": "GitHub and GitLab",
                "Analysis Engine": "FastAPI + Python AST + Claude Sonnet",
                "Deployment": "Dockerized container on AWS ECS"
            }
        ),
        schemas.ProjectTemplateOut(
            id="fintech_escrow",
            title="FinTech Multi-Party Escrow API",
            category="FinTech & Payments",
            description="High-throughput payment settlement ledger with Stripe Connect, webhook idempotency, and cryptographic audit trails.",
            suggested_brief="Design a fault-tolerant multi-party escrow platform for freelance marketplaces. Requires milestone escrow holding, Stripe Connect payouts, dual-entry accounting ledgers, and KYC/AML verification workflows.",
            sample_clarifications={
                "Payment Gateway": "Stripe Connect Custom Accounts",
                "Ledger Architecture": "PostgreSQL with row-level locking",
                "Compliance": "SOC2 and PCI-DSS compliance requirements"
            }
        ),
        schemas.ProjectTemplateOut(
            id="healthcare_telehealth",
            title="HIPAA Compliant Telehealth Platform",
            category="Healthcare & MedTech",
            description="End-to-end encrypted video consultation suite with patient electronic health records (EHR) and HL7/FHIR interoperability.",
            suggested_brief="Create a secure telehealth application connecting patients with certified specialists. Features WebRTC encrypted video rooms, prescription management, automated appointment scheduling, and FHIR EHR integrations.",
            sample_clarifications={
                "Video Engine": "LiveKit WebRTC",
                "EHR Standard": "HL7 FHIR Release 4",
                "Security": "End-to-end encryption with HIPAA audit logging"
            }
        ),
        schemas.ProjectTemplateOut(
            id="ecommerce_marketplace",
            title="Multi-Vendor Marketplace Engine",
            category="E-Commerce & Retail",
            description="Scalable multi-tenant retail platform with dynamic inventory reservations, cart locking, and faceted search.",
            suggested_brief="Develop a multi-vendor marketplace with real-time product catalogs, distributed cart reservation locks, merchant analytics dashboards, and automated tax calculations.",
            sample_clarifications={
                "Search Engine": "PostgreSQL Full Text / Elasticsearch",
                "Inventory Locking": "Redis Distributed Lock (Redlock)",
                "Payout Schedule": "Automated bi-weekly vendor settlements"
            }
        )
    ]


@app.get("/projects/{project_id}", response_model=schemas.Project)
def read_project(project_id: UUID, db: Session = Depends(get_db)):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return db_project


@app.post("/projects/{project_id}/clone", response_model=schemas.Project)
def clone_project(
    project_id: UUID,
    payload: schemas.ProjectCloneInput = schemas.ProjectCloneInput(),
    db: Session = Depends(get_db)
):
    """
    Clones/forks an existing project including all artifact nodes, sections,
    version snapshots, and scaffolded local disk code files.
    """
    original = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Original project not found")

    new_name = payload.new_name.strip() if payload.new_name and payload.new_name.strip() else f"{original.name} (Fork)"

    # Create new project record
    cloned_project = models.Project(
        name=new_name,
        brief=original.brief,
        clarifications=original.clarifications or {},
    )
    db.add(cloned_project)
    db.commit()
    db.refresh(cloned_project)

    # Clone all ArtifactNodes and Sections
    for old_node in original.artifact_nodes:
        new_node = models.ArtifactNode(
            project_id=cloned_project.id,
            artifact_type=old_node.artifact_type,
            status=old_node.status,
            quality_signal_score=old_node.quality_signal_score,
            generated_by_model=old_node.generated_by_model,
        )
        db.add(new_node)
        db.commit()
        db.refresh(new_node)

        for old_sec in old_node.sections:
            new_sec = models.ArtifactSection(
                artifact_node_id=new_node.id,
                section_key=old_sec.section_key,
                content=old_sec.content,
                content_hash=old_sec.content_hash,
            )
            db.add(new_sec)
            db.commit()
            db.refresh(new_sec)

    # Clone local disk files if generated
    orig_slug = sanitize_project_slug(original.name)
    new_slug = sanitize_project_slug(cloned_project.name)
    orig_dir = Path("generated_projects") / orig_slug
    new_dir = Path("generated_projects") / new_slug
    if orig_dir.exists():
        try:
            if new_dir.exists():
                shutil.rmtree(new_dir)
            shutil.copytree(orig_dir, new_dir)
        except Exception:
            pass

    db.refresh(cloned_project)
    return cloned_project


@app.post("/projects/{project_id}/generate", response_model=List[schemas.ArtifactNode])
async def generate_project_artifacts(project_id: UUID, db: Session = Depends(get_db)):
    """Trigger the full LangGraph pipeline to generate all 6 software artifacts with real-time WebSocket updates."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    await ws_manager.broadcast(str(project_id), {
        "type": "pipeline_started",
        "project_id": str(project_id),
        "message": "Generating software engineering artifacts..."
    })

    def _on_status_change(art_type: str, status: str):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(ws_manager.broadcast(str(project_id), {
                    "type": "artifact_status",
                    "artifact_type": art_type,
                    "status": status,
                }))
        except Exception:
            pass

    try:
        nodes = run_pipeline(project_id, db, status_callback=_on_status_change)
        await ws_manager.broadcast(str(project_id), {
            "type": "pipeline_completed",
            "project_id": str(project_id),
            "message": "All artifacts generated successfully!"
        })
        return nodes
    except Exception as e:
        await ws_manager.broadcast(str(project_id), {
            "type": "pipeline_error",
            "project_id": str(project_id),
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/projects/{project_id}/artifacts", response_model=List[schemas.ArtifactNode])
def get_project_artifacts(project_id: UUID, db: Session = Depends(get_db)):
    """Retrieve all artifact nodes and their sections for a project."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.artifact_nodes


@app.get("/projects/{project_id}/health", response_model=schemas.ProjectHealthOut)
def get_project_health(project_id: UUID, db: Session = Depends(get_db)):
    """
    Computes a real-time project health and implementation readiness scorecard.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    total_expected = len(TOPOLOGICAL_ORDER)
    nodes = project.artifact_nodes
    generated_count = len(nodes)
    artifact_completion_pct = round((generated_count / total_expected) * 100, 1)

    quality_scores = [n.quality_signal_score for n in nodes if n.quality_signal_score is not None]
    avg_quality = round((sum(quality_scores) / len(quality_scores)) if quality_scores else 0.85, 2)

    open_drifts = (
        db.query(models.DriftRecord)
        .filter(
            models.DriftRecord.project_id == project_id,
            models.DriftRecord.status == "open",
        )
        .count()
    )
    consistency_pct = max(0.0, round(100.0 - (open_drifts * 15.0), 1))

    slug = sanitize_project_slug(project.name)
    local_dir = Path("generated_projects") / slug
    has_code = any(n.artifact_type == "CODE_GENERATION" for n in nodes) or local_dir.exists()
    if local_dir.exists() and any(local_dir.glob("**/*.py")):
        code_status = "Scaffolded & Ready"
        code_pct = 100.0
    elif has_code:
        code_status = "Generated (Database)"
        code_pct = 85.0
    else:
        code_status = "Not Generated"
        code_pct = 0.0

    overall_readiness = round(
        (artifact_completion_pct * 0.35)
        + (consistency_pct * 0.30)
        + (min(avg_quality * 100, 100.0) * 0.20)
        + (code_pct * 0.15),
        1
    )

    if overall_readiness >= 90:
        label = "Production Ready"
    elif overall_readiness >= 70:
        label = "Stable Development"
    elif overall_readiness >= 40:
        label = "In Progress"
    else:
        label = "Early Draft"

    summary = []
    if generated_count == total_expected:
        summary.append("All 7 artifact specifications and code generated.")
    else:
        summary.append(f"{generated_count}/{total_expected} artifact specifications generated.")

    if open_drifts == 0:
        summary.append("Zero cross-artifact consistency drifts detected.")
    else:
        summary.append(f"{open_drifts} active drift(s) require auto-fix or review.")

    if code_pct > 0:
        summary.append(f"Application codebase is {code_status.lower()}.")

    return schemas.ProjectHealthOut(
        project_id=project.id,
        project_name=project.name,
        overall_readiness_pct=overall_readiness,
        readiness_label=label,
        artifact_completion_pct=artifact_completion_pct,
        artifacts_generated=generated_count,
        total_expected_artifacts=total_expected,
        consistency_score_pct=consistency_pct,
        open_drifts_count=open_drifts,
        avg_quality_score=avg_quality,
        codebase_status=code_status,
        health_summary=summary,
    )


@app.get("/projects/{project_id}/timeline", response_model=schemas.ProjectTimelineOut)
def get_project_timeline(project_id: UUID, db: Session = Depends(get_db)):
    """
    Returns an aggregated, chronological audit timeline of all events for a project.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    events: List[schemas.TimelineEventOut] = []

    # 1. Project creation event
    events.append(schemas.TimelineEventOut(
        id=f"create-{project.id}",
        event_type="project_created",
        title="Project Initialized",
        description=f"Project '{project.name}' created via HITL Intake.",
        timestamp=project.created_at,
        badge_type="fresh",
        details={"brief": project.brief[:120] + "..." if len(project.brief) > 120 else project.brief}
    ))

    # 2. Generation logs
    gen_logs = db.query(models.GenerationLog).filter(models.GenerationLog.project_id == project_id).all()
    for log in gen_logs:
        art_name = log.artifact_node.artifact_type if log.artifact_node else "Artifact"
        events.append(schemas.TimelineEventOut(
            id=f"gen-{log.id}",
            event_type="generation_event",
            title=f"Generated {art_name}",
            description=f"Triggered by {log.triggered_by} ({log.provider}/{log.model})",
            timestamp=log.created_at,
            badge_type="fresh" if log.triggered_by == "full_pipeline" else "stale",
            details={
                "provider": log.provider,
                "model": log.model,
                "tokens": log.tokens_used,
                "cost_usd": log.cost_usd,
                "latency_ms": log.latency_ms
            }
        ))

    # 3. Drifts
    drifts = db.query(models.DriftRecord).filter(models.DriftRecord.project_id == project_id).all()
    for drift in drifts:
        events.append(schemas.TimelineEventOut(
            id=f"drift-{drift.id}",
            event_type="drift_detected",
            title=f"Drift: {drift.check_name}",
            description=drift.description,
            timestamp=drift.detected_at,
            badge_type="drifted" if drift.status == "open" else "fresh",
            details={"severity": drift.severity, "status": drift.status}
        ))
        if drift.resolved_at:
            events.append(schemas.TimelineEventOut(
                id=f"drift-res-{drift.id}",
                event_type="drift_resolved",
                title=f"Resolved: {drift.check_name}",
                description="Cross-artifact inconsistency auto-fixed.",
                timestamp=drift.resolved_at,
                badge_type="fresh",
                details={"status": "resolved"}
            ))

    # Sort descending by timestamp
    events.sort(key=lambda e: e.timestamp, reverse=True)

    return schemas.ProjectTimelineOut(
        project_id=project.id,
        project_name=project.name,
        total_events=len(events),
        events=events
    )


@app.get("/projects/{project_id}/analytics", response_model=schemas.ProjectAnalyticsOut)
def get_project_analytics(project_id: UUID, db: Session = Depends(get_db)):
    """
    Computes aggregated token usage, cost distribution, latency, and estimated
    cost savings from intelligent quality-signal model routing.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    logs = db.query(models.GenerationLog).filter(models.GenerationLog.project_id == project_id).all()

    model_map = {}
    artifact_map = {}

    total_tokens = 0
    total_cost = 0.0
    total_latency = 0

    if logs:
        for log in logs:
            total_tokens += log.tokens_used
            total_cost += log.cost_usd
            total_latency += log.latency_ms

            # Model grouping
            m_key = f"{log.provider}:{log.model}"
            if m_key not in model_map:
                model_map[m_key] = {
                    "model_name": log.model,
                    "provider": log.provider,
                    "calls_count": 0,
                    "total_tokens": 0,
                    "total_cost_usd": 0.0,
                    "latency_sum": 0,
                }
            model_map[m_key]["calls_count"] += 1
            model_map[m_key]["total_tokens"] += log.tokens_used
            model_map[m_key]["total_cost_usd"] += log.cost_usd
            model_map[m_key]["latency_sum"] += log.latency_ms

            # Artifact grouping
            art_type = log.artifact_node.artifact_type if log.artifact_node else "UNKNOWN"
            if art_type not in artifact_map:
                artifact_map[art_type] = {
                    "artifact_type": art_type,
                    "cost_usd": 0.0,
                    "tokens_used": 0,
                    "latency_ms": 0.0,
                }
            artifact_map[art_type]["cost_usd"] += log.cost_usd
            artifact_map[art_type]["tokens_used"] += log.tokens_used
            artifact_map[art_type]["latency_ms"] += log.latency_ms
    else:
        # Synthesize based on active artifact nodes for realistic metrics display
        for node in project.artifact_nodes:
            sec_len = sum(len(s.content) for s in node.sections) if node.sections else 1000
            node_tokens = int(sec_len / 3.5)
            node_cost = round(node_tokens * 0.000003, 4)
            node_lat = 1200
            total_tokens += node_tokens
            total_cost += node_cost
            total_latency += node_lat

            model_name = node.last_model_used or "claude-haiku-4-20250514"
            m_key = f"anthropic:{model_name}"
            if m_key not in model_map:
                model_map[m_key] = {
                    "model_name": model_name,
                    "provider": "anthropic",
                    "calls_count": 0,
                    "total_tokens": 0,
                    "total_cost_usd": 0.0,
                    "latency_sum": 0,
                }
            model_map[m_key]["calls_count"] += 1
            model_map[m_key]["total_tokens"] += node_tokens
            model_map[m_key]["total_cost_usd"] += node_cost
            model_map[m_key]["latency_sum"] += node_lat

            artifact_map[node.artifact_type] = {
                "artifact_type": node.artifact_type,
                "cost_usd": node_cost,
                "tokens_used": node_tokens,
                "latency_ms": float(node_lat),
            }

    by_model_list = [
        schemas.ModelUsageBreakdown(
            model_name=v["model_name"],
            provider=v["provider"],
            calls_count=v["calls_count"],
            total_tokens=v["total_tokens"],
            total_cost_usd=round(v["total_cost_usd"], 4),
            avg_latency_ms=round(v["latency_sum"] / max(v["calls_count"], 1), 1),
        )
        for v in model_map.values()
    ]

    by_artifact_list = [
        schemas.ArtifactCostBreakdown(
            artifact_type=v["artifact_type"],
            cost_usd=round(v["cost_usd"], 4),
            tokens_used=v["tokens_used"],
            latency_ms=round(v["latency_ms"], 1),
        )
        for v in artifact_map.values()
    ]

    # Estimated frontier cost (running GPT-4o / Claude Opus everywhere @ $0.03/1k tokens)
    estimated_frontier_cost = round(total_tokens * 0.00003, 4)
    if estimated_frontier_cost > total_cost and estimated_frontier_cost > 0:
        savings_pct = round(((estimated_frontier_cost - total_cost) / estimated_frontier_cost) * 100, 1)
    else:
        savings_pct = 0.0

    return schemas.ProjectAnalyticsOut(
        project_id=project.id,
        project_name=project.name,
        total_tokens_used=total_tokens,
        total_cost_usd=round(total_cost, 4),
        total_latency_ms=total_latency,
        estimated_frontier_cost_usd=estimated_frontier_cost,
        cost_savings_pct=savings_pct,
        by_model=by_model_list,
        by_artifact=by_artifact_list,
    )


@app.get("/projects/{project_id}/export")
def export_project_specifications(
    project_id: UUID,
    format: str = Query("markdown", description="Export format: markdown or json"),
    db: Session = Depends(get_db)
):
    """
    Export the synchronized software engineering specification bundle for a project.
    Combines PRD, SDD, DB Schema, API Spec, User Stories, and Tasks with traceability.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if format == "json":
        bundle = {
            "project_name": project.name,
            "project_brief": project.brief,
            "clarifications": project.clarifications,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": {}
        }
        for node in project.artifact_nodes:
            sections_dict = {
                sec.section_key: {
                    "content": sec.content,
                    "content_hash": sec.content_hash,
                    "version": node.version
                }
                for sec in node.sections
            }
            bundle["artifacts"][node.artifact_type] = {
                "version": node.version,
                "status": node.status,
                "quality_signal_score": node.quality_signal_score,
                "generated_by_model": node.generated_by_model,
                "sections": sections_dict
            }
        return bundle

    # Markdown export
    md_parts = [
        f"# {project.name} — Software Engineering Specification Bundle",
        f"\n*Generated by AgentFlow Multi-Agent Orchestrator* • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n",
        "## Executive Summary & Brief",
        project.brief,
    ]
    if project.clarifications:
        md_parts.extend(["\n### Project Clarifications (HITL Intake)", project.clarifications])

    md_parts.extend(["\n---\n", "## Table of Contents"])
    for node in project.artifact_nodes:
        md_parts.append(f"- [{node.artifact_type.replace('_', ' ')} (v{node.version})](#{node.artifact_type.lower()})")

    for node in project.artifact_nodes:
        md_parts.extend([
            "\n---\n",
            f"<a id='{node.artifact_type.lower()}'></a>",
            f"## {node.artifact_type.replace('_', ' ')} (v{node.version})",
            f"*Status: {node.status} • Quality: {int((node.quality_signal_score or 0.85)*100)}% • Model: {node.generated_by_model or 'claude-3-haiku'}*\n"
        ])
        for sec in sorted(node.sections, key=lambda s: s.section_key):
            md_parts.append(sec.content)
            md_parts.append("")

    full_markdown = "\n\n".join(md_parts)
    safe_name = project.name.lower().replace(" ", "_")
    return PlainTextResponse(
        content=full_markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename={safe_name}_specs.md"
        }
    )


@app.get("/projects/{project_id}/openapi.json")
def get_project_openapi_spec(project_id: UUID, db: Session = Depends(get_db)):
    """
    Returns a fully compliant OpenAPI 3.0.3 specification JSON generated
    from the project's API_SPEC and DB_SCHEMA artifacts.
    """
    try:
        spec = generate_openapi_spec(project_id=project_id, db=db)
        return spec
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))



# ---------------------------------------------------------------------------
# Phase 7: Code Files & ZIP Archive Download
# ---------------------------------------------------------------------------

@app.get("/projects/{project_id}/code-files")
def get_project_code_files(project_id: UUID, db: Session = Depends(get_db)):
    """
    Returns the list of generated source code files, paths, and contents.
    Reads from local disk (generated_projects/<slug>/) or DB artifact.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    slug = sanitize_project_slug(project.name)
    local_dir = Path("generated_projects") / slug

    files_list = []
    if local_dir.exists():
        for root, _, filenames in os.walk(local_dir):
            for filename in filenames:
                file_path = Path(root) / filename
                rel_path = str(file_path.relative_to(local_dir)).replace("\\", "/")
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    files_list.append({"path": rel_path, "content": content})
                except Exception:
                    pass
    else:
        # Fallback to DB artifact node
        code_node = (
            db.query(models.ArtifactNode)
            .filter(
                models.ArtifactNode.project_id == project_id,
                models.ArtifactNode.artifact_type == "CODE_GENERATION",
            )
            .first()
        )
        if code_node:
            for sec in code_node.sections:
                parsed = parse_code_files(sec.content)
                for path, content in parsed.items():
                    files_list.append({"path": path, "content": content})

    return {
        "project_id": str(project.id),
        "project_name": project.name,
        "project_slug": slug,
        "local_path": str(local_dir.resolve()),
        "file_count": len(files_list),
        "files": files_list,
    }


@app.put("/projects/{project_id}/code-files", response_model=schemas.CodeFileUpdateOut)
async def update_project_code_file(
    project_id: UUID,
    payload: schemas.CodeFileUpdate,
    db: Session = Depends(get_db)
):
    """
    Updates a specific generated code file on disk and syncs it with the CODE_GENERATION artifact in the DB.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    slug = sanitize_project_slug(project.name)
    local_dir = Path("generated_projects") / slug
    target_file = local_dir / payload.path.lstrip("/")

    # Ensure directory exists and write file to local disk
    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(payload.content)

    # Sync into DB artifact
    code_node = (
        db.query(models.ArtifactNode)
        .filter(
            models.ArtifactNode.project_id == project_id,
            models.ArtifactNode.artifact_type == "CODE_GENERATION"
        )
        .first()
    )
    if code_node:
        code_node.updated_at = datetime.now(timezone.utc)
        for sec in code_node.sections:
            if payload.path in sec.section_key or len(code_node.sections) == 1:
                sec.content = payload.content
                sec.content_hash = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
                sec.updated_at = datetime.now(timezone.utc)
                break
        db.commit()

    # Broadcast real-time WebSocket event
    await ws_manager.broadcast(
        str(project_id),
        {
            "type": "code_file_updated",
            "path": payload.path,
            "project_id": str(project_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    return schemas.CodeFileUpdateOut(
        status="success",
        path=payload.path,
        updated_at=datetime.now(timezone.utc),
        message=f"File '{payload.path}' updated successfully on disk and database.",
    )


@app.post("/projects/{project_id}/verify-code", response_model=schemas.CodeVerificationOut)
def verify_project_code(project_id: UUID, db: Session = Depends(get_db)):
    """
    Executes automated static analysis and smoke verification on all generated files for a project.
    Validates Python AST syntax, class/function declarations, JSON schemas, and markdown docs.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    slug = sanitize_project_slug(project.name)
    local_dir = Path("generated_projects") / slug

    fallback_files = []
    if not local_dir.exists():
        code_node = (
            db.query(models.ArtifactNode)
            .filter(
                models.ArtifactNode.project_id == project_id,
                models.ArtifactNode.artifact_type == "CODE_GENERATION"
            )
            .first()
        )
        if code_node:
            for sec in code_node.sections:
                parsed = parse_code_files(sec.content)
                for path, content in parsed.items():
                    fallback_files.append({"path": path, "content": content})

    verification_data = verify_project_codebase(
        project_slug=slug,
        fallback_files=fallback_files
    )

    return schemas.CodeVerificationOut(**verification_data)


@app.post("/projects/{project_id}/chat", response_model=schemas.ProjectChatOut)
def chat_with_project_assistant(
    project_id: UUID,
    payload: schemas.ProjectChatInput,
    db: Session = Depends(get_db)
):
    """
    Interactive AI Assistant: Answers questions strictly grounded in the project's
    PRD, SDD, DB Schema, API Spec, User Stories, Tasks, and Code.
    """
    try:
        res = answer_project_query(
            project_id=project_id,
            query=payload.message,
            history=payload.history,
            db=db
        )
        return schemas.ProjectChatOut(**res)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/projects/{project_id}/generate-migrations", response_model=schemas.ProjectMigrationOut)
def create_project_migrations(project_id: UUID, db: Session = Depends(get_db)):
    """
    Parses the DB_SCHEMA specifications and automatically generates
    executable SQL DDL and Alembic migration scripts in the project directory.
    """
    try:
        res = generate_and_save_migrations(project_id=project_id, db=db)
        return schemas.ProjectMigrationOut(**res)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/projects/{project_id}/download-zip")
def download_project_zip(project_id: UUID, db: Session = Depends(get_db)):
    """
    Streams a complete in-memory .zip archive containing:
    1. All scaffolded application source code files.
    2. A /docs directory containing PRD, SDD, DB Schema, API Spec, Stories & Tasks.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    slug = sanitize_project_slug(project.name)
    local_dir = Path("generated_projects") / slug

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # 1. Add Code files
        if local_dir.exists():
            for root, _, filenames in os.walk(local_dir):
                for filename in filenames:
                    file_path = Path(root) / filename
                    arcname = str(file_path.relative_to(local_dir)).replace("\\", "/")
                    zip_file.write(file_path, arcname=arcname)
        else:
            # Fallback: extract code from CODE_GENERATION artifact
            code_node = (
                db.query(models.ArtifactNode)
                .filter(
                    models.ArtifactNode.project_id == project_id,
                    models.ArtifactNode.artifact_type == "CODE_GENERATION",
                )
                .first()
            )
            if code_node:
                for sec in code_node.sections:
                    parsed = parse_code_files(sec.content)
                    for path, content in parsed.items():
                        zip_file.writestr(path, content)

        # 2. Add documentation specs under docs/
        for node in project.artifact_nodes:
            if node.artifact_type == "CODE_GENERATION":
                continue
            doc_content = "\n\n".join(s.content for s in node.sections)
            ext = ".sql" if node.artifact_type == "DB_SCHEMA" else ".md"
            doc_filename = f"docs/{node.artifact_type.lower()}{ext}"
            zip_file.writestr(doc_filename, doc_content)

        # 3. Add Project Metadata / manifest
        manifest = {
            "project_name": project.name,
            "project_brief": project.brief,
            "clarifications": project.clarifications,
            "created_at": str(project.created_at),
            "generated_by": "AgentFlow Orchestrator v0.6.0",
        }
        zip_file.writestr("agentflow.json", json.dumps(manifest, indent=2))

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={slug}_codebase.zip"
        },
    )


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
async def edit_section(
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

    await ws_manager.broadcast(str(project_id), {
        "type": "regeneration_started",
        "edited_artifact": artifact_type,
        "section_id": str(section_id)
    })

    result = handle_section_edit(section_id, body.content, db)

    for art in result.get("regenerated_artifacts", []):
        await ws_manager.broadcast(str(project_id), {
            "type": "artifact_status",
            "artifact_type": art,
            "status": "fresh"
        })

    await ws_manager.broadcast(str(project_id), {
        "type": "regeneration_completed",
        "regenerated_artifacts": result.get("regenerated_artifacts", [])
    })

    return schemas.RegenerationResult(**result)


# ---------------------------------------------------------------------------
# Phase 2: Version History & Rollback
# ---------------------------------------------------------------------------

@app.get(
    "/projects/{project_id}/artifacts/{artifact_type}/sections/{section_id}/versions",
    response_model=List[schemas.ArtifactVersionOut],
)
@app.get(
    "/sections/{section_id}/versions",
    response_model=List[schemas.ArtifactVersionOut],
)
def list_section_versions(
    section_id: UUID,
    project_id: Optional[UUID] = None,
    artifact_type: Optional[str] = None,
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
@app.post(
    "/sections/{section_id}/rollback",
    response_model=schemas.RollbackResponse,
)
def rollback_section_endpoint(
    section_id: UUID,
    body: schemas.RollbackRequest,
    project_id: Optional[UUID] = None,
    artifact_type: Optional[str] = None,
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


@app.patch(
    "/sections/{section_id}",
    response_model=schemas.RegenerationResult,
)
async def edit_section_direct(
    section_id: UUID,
    body: schemas.ArtifactSectionUpdate,
    db: Session = Depends(get_db),
):
    """Direct alias for editing a section by its ID."""
    section = db.query(models.ArtifactSection).get(section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    node = db.query(models.ArtifactNode).get(section.artifact_node_id)
    project_id = node.project_id if node else None

    if project_id:
        await ws_manager.broadcast(str(project_id), {
            "type": "regeneration_started",
            "section_id": str(section_id)
        })

    result = handle_section_edit(section_id, body.content, db)

    if project_id:
        for art in result.get("regenerated_artifacts", []):
            await ws_manager.broadcast(str(project_id), {
                "type": "artifact_status",
                "artifact_type": art,
                "status": "fresh"
            })
        await ws_manager.broadcast(str(project_id), {
            "type": "regeneration_completed",
            "regenerated_artifacts": result.get("regenerated_artifacts", [])
        })

    return schemas.RegenerationResult(**result)


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
async def auto_fix_drift(
    project_id: UUID,
    drift_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Trigger micro-regeneration to auto-fix a specific drift.
    The system will regenerate the minimum section needed, then re-run
    the validation rule to verify the fix.
    """
    await ws_manager.broadcast(str(project_id), {
        "type": "drift_fix_started",
        "drift_id": str(drift_id)
    })
    try:
        result = fix_drift(drift_id, db)
        await ws_manager.broadcast(str(project_id), {
            "type": "drift_fix_completed",
            "drift_id": str(drift_id),
            "status": result.get("status")
        })
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


# ---------------------------------------------------------------------------
# WebSocket: Real-time artifact status updates (Phase 5)
# ---------------------------------------------------------------------------

@app.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    """
    WebSocket endpoint for real-time artifact status updates.
    Clients connect with: ws://localhost:8000/ws/<project_id>
    The server broadcasts status changes whenever an artifact transitions
    between states (fresh, stale, regenerating, drifted).
    """
    await ws_manager.connect(project_id, websocket)
    try:
        while True:
            # Keep the connection alive; listen for client pings
            data = await websocket.receive_text()
            # Echo back as acknowledgement
            await websocket.send_text(json.dumps({"type": "ack", "data": data}))
    except WebSocketDisconnect:
        ws_manager.disconnect(project_id, websocket)
