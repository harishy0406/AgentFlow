from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from . import models, schemas
from .database import engine, get_db
from .agents.graph_engine import ARTIFACT_DEPENDENCY_MAP
from .agents.orchestrator import handle_section_edit, rollback_section

# Create database tables (in a real app, use alembic)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AgentFlow API", version="0.2.0")


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
