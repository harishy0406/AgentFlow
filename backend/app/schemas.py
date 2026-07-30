from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Artifact Sections
# ---------------------------------------------------------------------------

class ArtifactSectionBase(BaseModel):
    section_key: str
    content: str
    content_hash: str

class ArtifactSectionCreate(ArtifactSectionBase):
    pass

class ArtifactSectionUpdate(BaseModel):
    """Used for PATCH /sections/{section_id}"""
    content: str

class ArtifactSection(ArtifactSectionBase):
    id: UUID
    artifact_node_id: UUID
    updated_at: datetime
    traces_to_ids: List[UUID] = []  # simplified list of upstream IDs

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Artifact Nodes
# ---------------------------------------------------------------------------

class ArtifactNodeBase(BaseModel):
    artifact_type: str
    version: int = 1
    status: str = "fresh"
    quality_signal_score: Optional[float] = None
    generated_by_model: Optional[str] = None

class ArtifactNodeCreate(ArtifactNodeBase):
    project_id: UUID

class ArtifactNode(ArtifactNodeBase):
    id: UUID
    project_id: UUID
    updated_at: datetime
    sections: List[ArtifactSection] = []

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectBase(BaseModel):
    name: str
    brief: str

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    id: UUID
    created_at: datetime
    artifact_nodes: List[ArtifactNode] = []

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Phase 2: Version history & rollback
# ---------------------------------------------------------------------------

class ArtifactVersionOut(BaseModel):
    id: UUID
    artifact_node_id: UUID
    section_id: UUID
    version: int
    content: str
    content_hash: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RollbackRequest(BaseModel):
    """Request body for rolling back a section to a prior version."""
    target_version: int


class RollbackResponse(BaseModel):
    section_id: str
    rolled_back_to_version: int
    content: str


# ---------------------------------------------------------------------------
# Phase 2: Selective regeneration response
# ---------------------------------------------------------------------------

class RegenerationResult(BaseModel):
    """Returned by the section-edit endpoint to describe what was regenerated."""
    edited_section_id: str
    content_changed: bool
    dirty_sections: List[str] = []
    regenerated_artifacts: List[str] = []


# ---------------------------------------------------------------------------
# Phase 2: Dependency graph view
# ---------------------------------------------------------------------------

class GraphNodeOut(BaseModel):
    """Simplified node representation for the graph visualization endpoint."""
    id: UUID
    artifact_type: str
    version: int
    status: str
    section_count: int

class GraphEdgeOut(BaseModel):
    """An edge in the dependency graph."""
    from_artifact_type: str
    to_artifact_type: str

class DependencyGraphOut(BaseModel):
    """Full graph payload returned by GET /projects/{id}/graph."""
    nodes: List[GraphNodeOut]
    edges: List[GraphEdgeOut]
