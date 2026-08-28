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


@app.get("/projects", response_model=List[schemas.Project])
@app.get("/projects/", response_model=List[schemas.Project])
def list_projects(db: Session = Depends(get_db)):
    """List all projects in descending order of creation."""
    return db.query(models.Project).order_by(models.Project.created_at.desc()).all()


@app.get("/projects/{project_id}", response_model=schemas.Project)
def read_project(project_id: UUID, db: Session = Depends(get_db)):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return db_project


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
