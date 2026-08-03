import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, ForeignKey, DateTime, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .database import Base

class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    brief = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    artifact_nodes = relationship("ArtifactNode", back_populates="project", cascade="all, delete-orphan")


class ArtifactNode(Base):
    __tablename__ = "artifact_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    artifact_type = Column(String, nullable=False) # 'PRD','SDD','DB_SCHEMA','API_SPEC','USER_STORIES','TASKS'
    version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="fresh") # 'fresh','stale','regenerating','drifted'
    quality_signal_score = Column(Float, nullable=True)
    generated_by_model = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="artifact_nodes")
    sections = relationship("ArtifactSection", back_populates="artifact_node", cascade="all, delete-orphan")


# Association table for section traces
section_traces = Table(
    "section_traces",
    Base.metadata,
    Column("downstream_section_id", UUID(as_uuid=True), ForeignKey("artifact_sections.id"), primary_key=True),
    Column("upstream_section_id", UUID(as_uuid=True), ForeignKey("artifact_sections.id"), primary_key=True)
)


class ArtifactSection(Base):
    __tablename__ = "artifact_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artifact_node_id = Column(UUID(as_uuid=True), ForeignKey("artifact_nodes.id"), nullable=False)
    section_key = Column(String, nullable=False)
    content = Column(String, nullable=False)
    content_hash = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    artifact_node = relationship("ArtifactNode", back_populates="sections")
    
    # Self-referential many-to-many relationship for traces
    # This section (downstream) traces to upstream sections
    traces_to = relationship(
        "ArtifactSection",
        secondary=section_traces,
        primaryjoin=id==section_traces.c.downstream_section_id,
        secondaryjoin=id==section_traces.c.upstream_section_id,
        backref="traced_by" # Upstream section is traced by these downstream sections
    )


class ArtifactVersion(Base):
    """Stores a snapshot of an artifact section before each regeneration,
    enabling rollback to any prior version."""
    __tablename__ = "artifact_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artifact_node_id = Column(UUID(as_uuid=True), ForeignKey("artifact_nodes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("artifact_sections.id"), nullable=False)
    version = Column(Integer, nullable=False)
    content = Column(String, nullable=False)
    content_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    artifact_node = relationship("ArtifactNode")
    section = relationship("ArtifactSection")


class GenerationLog(Base):
    """Logs every generation / regeneration event for observability."""
    __tablename__ = "generation_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    artifact_node_id = Column(UUID(as_uuid=True), ForeignKey("artifact_nodes.id"), nullable=False)
    triggered_by = Column(String, nullable=False)  # 'initial_generation', 'selective_regeneration', 'micro_regeneration'
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    tokens_used = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    project = relationship("Project")
    artifact_node = relationship("ArtifactNode")


class DriftRecord(Base):
    """Logs cross-artifact consistency drift detected by the Auditor (Phase 4)."""
    __tablename__ = "drift_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    check_name = Column(String, nullable=False)  # e.g. 'requirement_coverage', 'schema_endpoint_mapping'
    artifact_a_id = Column(UUID(as_uuid=True), ForeignKey("artifact_nodes.id"), nullable=False)
    artifact_b_id = Column(UUID(as_uuid=True), ForeignKey("artifact_nodes.id"), nullable=False)
    section_a_id = Column(UUID(as_uuid=True), ForeignKey("artifact_sections.id"), nullable=True)
    section_b_id = Column(UUID(as_uuid=True), ForeignKey("artifact_sections.id"), nullable=True)
    description = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="medium")  # 'low', 'medium', 'high'
    status = Column(String, nullable=False, default="open")  # 'open', 'auto_fixed', 'dismissed'
    detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project")
    artifact_a = relationship("ArtifactNode", foreign_keys=[artifact_a_id])
    artifact_b = relationship("ArtifactNode", foreign_keys=[artifact_b_id])

