"""
Selective Regeneration Orchestrator — Phase 2

This module ties together the dependency graph engine and the agent nodes
to perform diff-aware selective regeneration when a user edits a section.

Flow:
1. User edits a section → PATCH endpoint calls `handle_section_edit`
2. Compute new hash, check if content actually changed
3. Save a version snapshot of the old content (for rollback)
4. BFS the dependency graph to find all downstream dirty sections
5. Mark dirty nodes as "stale"
6. For each dirty section in topological order:
   a. Compute the diff summary between old and new upstream content
   b. Invoke the owning agent with the regen prompt
   c. Update the section content + hash, bump version, mark fresh
7. Return a summary of what was regenerated
"""

import time
from uuid import UUID
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from ..models import (
    ArtifactNode, ArtifactSection, ArtifactVersion, GenerationLog, Project
)
from .graph_engine import (
    compute_content_hash,
    compute_diff_summary,
    recompute_subgraph,
    mark_sections_stale,
    mark_node_fresh,
    TOPOLOGICAL_ORDER,
)
from .prompts import (
    BUSINESS_ANALYST_REGEN_PROMPT,
    SYSTEM_DESIGNER_REGEN_PROMPT,
    DATABASE_ARCHITECT_REGEN_PROMPT,
    API_DESIGNER_REGEN_PROMPT,
    QA_ENGINEER_REGEN_PROMPT,
    PROJECT_PLANNER_REGEN_PROMPT,
)


# Map artifact types to their regeneration prompts
REGEN_PROMPT_MAP = {
    "PRD":          BUSINESS_ANALYST_REGEN_PROMPT,
    "SDD":          SYSTEM_DESIGNER_REGEN_PROMPT,
    "DB_SCHEMA":    DATABASE_ARCHITECT_REGEN_PROMPT,
    "API_SPEC":     API_DESIGNER_REGEN_PROMPT,
    "USER_STORIES": QA_ENGINEER_REGEN_PROMPT,
    "TASKS":        PROJECT_PLANNER_REGEN_PROMPT,
}


def _get_llm():
    """Single-model provider for Phase 1/2. Phase 3 replaces this with the router."""
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)


def _get_full_artifact_content(
    project_id: UUID,
    artifact_type: str,
    db: Session,
) -> str:
    """Concatenate all sections of an artifact into a single string."""
    node = (
        db.query(ArtifactNode)
        .filter(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type,
        )
        .first()
    )
    if node is None:
        return ""
    sections = (
        db.query(ArtifactSection)
        .filter(ArtifactSection.artifact_node_id == node.id)
        .order_by(ArtifactSection.section_key)
        .all()
    )
    return "\n\n".join(s.content for s in sections)


def _save_version_snapshot(
    section: ArtifactSection,
    db: Session,
) -> None:
    """Persist a snapshot of the section before it is overwritten."""
    node = db.query(ArtifactNode).get(section.artifact_node_id)
    version = ArtifactVersion(
        artifact_node_id=section.artifact_node_id,
        section_id=section.id,
        version=node.version if node else 1,
        content=section.content,
        content_hash=section.content_hash,
    )
    db.add(version)
    # Don't commit yet; caller batches


def _build_regen_context(
    artifact_type: str,
    project_id: UUID,
    diff_summary: str,
    prior_content: str,
    db: Session,
) -> Dict[str, str]:
    """Build the template variables for the regeneration prompt."""
    ctx: Dict[str, str] = {
        "diff_summary": diff_summary,
        "prior_content": prior_content,
    }

    # Each prompt needs different upstream artifacts for reference
    if artifact_type == "PRD":
        project = db.query(Project).get(project_id)
        ctx["project_brief"] = project.brief if project else ""
    elif artifact_type == "SDD":
        ctx["prd"] = _get_full_artifact_content(project_id, "PRD", db)
    elif artifact_type == "DB_SCHEMA":
        ctx["sdd"] = _get_full_artifact_content(project_id, "SDD", db)
    elif artifact_type == "API_SPEC":
        ctx["sdd"] = _get_full_artifact_content(project_id, "SDD", db)
        ctx["db_schema"] = _get_full_artifact_content(project_id, "DB_SCHEMA", db)
    elif artifact_type == "USER_STORIES":
        ctx["prd"] = _get_full_artifact_content(project_id, "PRD", db)
        ctx["api_spec"] = _get_full_artifact_content(project_id, "API_SPEC", db)
    elif artifact_type == "TASKS":
        ctx["user_stories"] = _get_full_artifact_content(project_id, "USER_STORIES", db)
        ctx["api_spec"] = _get_full_artifact_content(project_id, "API_SPEC", db)

    return ctx


def _log_generation(
    project_id: UUID,
    node_id: UUID,
    latency_ms: int,
    db: Session,
) -> None:
    """Log a selective regeneration event."""
    log = GenerationLog(
        project_id=project_id,
        artifact_node_id=node_id,
        triggered_by="selective_regeneration",
        provider="openai",
        model="gpt-4o-mini",
        latency_ms=latency_ms,
    )
    db.add(log)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def handle_section_edit(
    section_id: UUID,
    new_content: str,
    db: Session,
) -> Dict[str, Any]:
    """
    Main entry point for Phase 2 selective regeneration.

    1. Validate the edit
    2. Snapshot the old version
    3. Update the section
    4. BFS to find dirty downstream sections
    5. Regenerate each dirty section in topological order
    6. Return a summary

    Returns a dict with keys:
      - edited_section_id
      - content_changed: bool
      - dirty_sections: list of regenerated section ids
      - regenerated_artifacts: list of artifact types that were touched
    """
    section = db.query(ArtifactSection).get(section_id)
    if section is None:
        raise ValueError(f"Section {section_id} not found")

    old_content = section.content
    old_hash = section.content_hash
    new_hash = compute_content_hash(new_content)

    # No change → nothing to do
    if old_hash == new_hash:
        return {
            "edited_section_id": str(section_id),
            "content_changed": False,
            "dirty_sections": [],
            "regenerated_artifacts": [],
        }

    # --- Step 1: snapshot the old version ---
    _save_version_snapshot(section, db)

    # --- Step 2: apply the edit ---
    section.content = new_content
    section.content_hash = new_hash
    section.updated_at = datetime.now(timezone.utc)
    db.commit()

    # --- Step 3: find downstream dirty sections ---
    # We exclude the edited section itself — it was already updated by the user
    all_dirty = recompute_subgraph(section_id, db)
    downstream_dirty = [sid for sid in all_dirty if sid != section_id]

    if not downstream_dirty:
        # The edit only affects the edited section (leaf node); no propagation needed
        node = db.query(ArtifactNode).get(section.artifact_node_id)
        if node:
            node.version += 1
            db.commit()
        return {
            "edited_section_id": str(section_id),
            "content_changed": True,
            "dirty_sections": [],
            "regenerated_artifacts": [],
        }

    # --- Step 4: mark downstream as stale ---
    mark_sections_stale(downstream_dirty, db)

    # --- Step 5: regenerate each dirty section in topological order ---
    regenerated_artifacts = []
    llm = _get_llm()

    diff_summary = compute_diff_summary(old_content, new_content)

    for dirty_sid in downstream_dirty:
        dirty_section = db.query(ArtifactSection).get(dirty_sid)
        if dirty_section is None:
            continue

        dirty_node = db.query(ArtifactNode).get(dirty_section.artifact_node_id)
        if dirty_node is None:
            continue

        artifact_type = dirty_node.artifact_type
        prompt_template_str = REGEN_PROMPT_MAP.get(artifact_type)
        if not prompt_template_str:
            continue

        # Snapshot before overwrite
        _save_version_snapshot(dirty_section, db)

        # Build context
        ctx = _build_regen_context(
            artifact_type,
            dirty_node.project_id,
            diff_summary,
            dirty_section.content,
            db,
        )

        # Invoke LLM
        prompt = PromptTemplate.from_template(prompt_template_str)
        chain = prompt | llm

        start_ms = int(time.time() * 1000)
        response = chain.invoke(ctx)
        end_ms = int(time.time() * 1000)

        # Update section
        new_regen_content = response.content
        dirty_section.content = new_regen_content
        dirty_section.content_hash = compute_content_hash(new_regen_content)
        dirty_section.updated_at = datetime.now(timezone.utc)

        # Bump version on the parent node
        dirty_node.version += 1
        dirty_node.status = "fresh"

        # Log the generation
        _log_generation(
            dirty_node.project_id,
            dirty_node.id,
            end_ms - start_ms,
            db,
        )

        if artifact_type not in regenerated_artifacts:
            regenerated_artifacts.append(artifact_type)

    db.commit()

    return {
        "edited_section_id": str(section_id),
        "content_changed": True,
        "dirty_sections": [str(sid) for sid in downstream_dirty],
        "regenerated_artifacts": regenerated_artifacts,
    }


def rollback_section(
    section_id: UUID,
    target_version: int,
    db: Session,
) -> Dict[str, Any]:
    """
    Rollback a section to a specific prior version.
    Returns the restored content.
    """
    version_record = (
        db.query(ArtifactVersion)
        .filter(
            ArtifactVersion.section_id == section_id,
            ArtifactVersion.version == target_version,
        )
        .first()
    )
    if version_record is None:
        raise ValueError(
            f"No version {target_version} found for section {section_id}"
        )

    section = db.query(ArtifactSection).get(section_id)
    if section is None:
        raise ValueError(f"Section {section_id} not found")

    # Snapshot current content before rollback
    _save_version_snapshot(section, db)

    section.content = version_record.content
    section.content_hash = version_record.content_hash
    section.updated_at = datetime.now(timezone.utc)

    node = db.query(ArtifactNode).get(section.artifact_node_id)
    if node:
        node.version += 1

    db.commit()

    return {
        "section_id": str(section_id),
        "rolled_back_to_version": target_version,
        "content": version_record.content,
    }
