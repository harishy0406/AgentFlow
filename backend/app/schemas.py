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


# ---------------------------------------------------------------------------
# Phase 3: Routing decisions
# ---------------------------------------------------------------------------

class RoutingDecisionOut(BaseModel):
    """A single routing decision made by the Quality-Signal Router."""
    artifact_type: str
    chosen_provider: str
    chosen_model: str
    predicted_quality_signal: float
    estimated_cost_usd: float
    rationale: str


class RegenerationResult(BaseModel):
    """Returned by the section-edit endpoint to describe what was regenerated."""
    edited_section_id: str
    content_changed: bool
    dirty_sections: List[str] = []
    regenerated_artifacts: List[str] = []
    routing_decisions: List[RoutingDecisionOut] = []


# ---------------------------------------------------------------------------
# Phase 3: Metrics
# ---------------------------------------------------------------------------

class ArtifactMetrics(BaseModel):
    """Per-artifact-type metrics."""
    artifact_type: str
    avg_quality_signal: Optional[float] = None
    total_generations: int = 0
    total_cost_usd: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    last_model_used: Optional[str] = None

class ProjectMetrics(BaseModel):
    """Per-project metrics response."""
    project_id: UUID
    total_cost_usd: Optional[float] = None
    total_generations: int = 0
    artifact_metrics: List[ArtifactMetrics] = []

class ProviderModelOut(BaseModel):
    """A model entry from the provider registry."""
    provider: str
    model_name: str
    cost_per_input_token: float
    cost_per_output_token: float
    max_context_tokens: int

class ProviderOut(BaseModel):
    """A provider entry from the registry."""
    name: str
    is_available: bool
    models: List[ProviderModelOut]


# ---------------------------------------------------------------------------
# Phase 4: Consistency Auditor & Drift Records
# ---------------------------------------------------------------------------

class DriftRecordOut(BaseModel):
    """Response model for a drift record."""
    id: UUID
    project_id: UUID
    check_name: str
    artifact_a_id: UUID
    artifact_b_id: UUID
    section_a_id: Optional[UUID] = None
    section_b_id: Optional[UUID] = None
    description: str
    severity: str
    status: str
    detected_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AuditRuleResult(BaseModel):
    """Result of running a single validation rule."""
    rule: str
    status: str
    severity: Optional[str] = None
    artifact_a: Optional[str] = None
    artifact_b: Optional[str] = None
    drifts_found: int = 0
    stale_cleared: Optional[int] = None
    drift_descriptions: List[str] = []
    reason: Optional[str] = None


class AuditResult(BaseModel):
    """Summary of a full audit run."""
    project_id: UUID
    total_rules_checked: int
    total_drifts_found: int
    rules: List[AuditRuleResult]


class DriftFixResult(BaseModel):
    """Result of a micro-regeneration auto-fix attempt."""
    drift_id: str
    status: str
    target_artifact: Optional[str] = None
    target_section_id: Optional[str] = None
    fix_verified: Optional[bool] = None
    latency_ms: Optional[int] = None
    model_used: Optional[str] = None
    message: Optional[str] = None


