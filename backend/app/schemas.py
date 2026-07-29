from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ArtifactSectionBase(BaseModel):
    section_key: str
    content: str
    content_hash: str

class ArtifactSectionCreate(ArtifactSectionBase):
    pass

class ArtifactSection(ArtifactSectionBase):
    id: UUID
    artifact_node_id: UUID
    updated_at: datetime
    traces_to_ids: List[UUID] = [] # simplified list of upstream IDs

    model_config = ConfigDict(from_attributes=True)


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
