"""
Dependency Graph Engine — Phase 2

Implements:
- Content hashing for artifact sections
- Diff computation between old and new section content
- BFS-based recompute_subgraph to find the minimal set of dirty sections
- Topological ordering of dirty sections for regeneration
"""

import hashlib
from uuid import UUID
from typing import List, Tuple, Dict, Set
from collections import defaultdict

from sqlalchemy.orm import Session

from ..models import ArtifactNode, ArtifactSection, section_traces


# ---------------------------------------------------------------------------
# Fixed artifact-type dependency graph
# ---------------------------------------------------------------------------
# Each entry maps an artifact type to its upstream dependencies.
# This mirrors the design doc topology:
#   PRD → SDD → DB_SCHEMA → API_SPEC → USER_STORIES → TASKS
#   PRD ──────────────────────────────→ USER_STORIES
ARTIFACT_DEPENDENCY_MAP: Dict[str, List[str]] = {
    "PRD":              [],
    "SDD":              ["PRD"],
    "DB_SCHEMA":        ["SDD"],
    "API_SPEC":         ["SDD", "DB_SCHEMA"],
    "USER_STORIES":     ["PRD", "API_SPEC"],
    "TASKS":            ["USER_STORIES", "API_SPEC"],
    "CODE_GENERATION":  ["DB_SCHEMA", "API_SPEC", "TASKS"],
}

# Reverse: artifact_type → list of downstream artifact types
ARTIFACT_DOWNSTREAM_MAP: Dict[str, List[str]] = defaultdict(list)
for _child, _parents in ARTIFACT_DEPENDENCY_MAP.items():
    for _parent in _parents:
        ARTIFACT_DOWNSTREAM_MAP[_parent].append(_child)

# Topological order for the fixed graph (used for ordering regeneration)
TOPOLOGICAL_ORDER: List[str] = [
    "PRD", "SDD", "DB_SCHEMA", "API_SPEC", "USER_STORIES", "TASKS", "CODE_GENERATION"
]


def compute_content_hash(content: str) -> str:
    """Compute a SHA-256 hash of the content string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_diff_summary(old_content: str, new_content: str) -> str:
    """
    Produce a human-readable diff summary between old and new content.
    This is what gets injected into the regeneration prompt so that
    downstream agents understand *what changed* without receiving the
    entire upstream document.
    """
    import difflib

    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile="previous_version",
        tofile="current_version",
        lineterm=""
    )
    diff_text = "\n".join(diff)

    if not diff_text.strip():
        return "No changes detected."

    return diff_text


def find_downstream_sections(
    section_id: UUID,
    db: Session,
) -> List[ArtifactSection]:
    """
    Find all sections whose traces_to relationship includes the given
    section_id (i.e. downstream sections that were derived from it).
    """
    section = db.query(ArtifactSection).get(section_id)
    if section is None:
        return []
    # traced_by is the backref defined on the ArtifactSection model
    return list(section.traced_by)


def recompute_subgraph(
    edited_section_id: UUID,
    db: Session,
) -> List[UUID]:
    """
    BFS from the edited section through the traces_to graph to find all
    downstream sections that need regeneration.

    Returns section IDs in a topologically-valid order (by artifact type
    first, then insertion order within each type).
    """
    dirty: Set[UUID] = {edited_section_id}
    frontier: List[UUID] = [edited_section_id]

    while frontier:
        current_id = frontier.pop(0)  # BFS (FIFO)
        downstream = find_downstream_sections(current_id, db)
        for sec in downstream:
            if sec.id not in dirty:
                dirty.add(sec.id)
                frontier.append(sec.id)

    # Order dirty sections by their artifact type's topological rank
    def _topo_key(sid: UUID) -> int:
        sec = db.query(ArtifactSection).get(sid)
        if sec is None:
            return 999
        node = db.query(ArtifactNode).get(sec.artifact_node_id)
        if node is None:
            return 999
        try:
            return TOPOLOGICAL_ORDER.index(node.artifact_type)
        except ValueError:
            return 999

    return sorted(dirty, key=_topo_key)


def get_dirty_artifact_types(
    dirty_section_ids: List[UUID],
    db: Session,
) -> List[str]:
    """
    Given a list of dirty section IDs, return the unique set of artifact
    types that contain at least one dirty section, in topological order.
    """
    types_seen: Set[str] = set()
    for sid in dirty_section_ids:
        sec = db.query(ArtifactSection).get(sid)
        if sec is None:
            continue
        node = db.query(ArtifactNode).get(sec.artifact_node_id)
        if node is not None:
            types_seen.add(node.artifact_type)

    return [t for t in TOPOLOGICAL_ORDER if t in types_seen]


def mark_sections_stale(
    section_ids: List[UUID],
    db: Session,
) -> None:
    """Mark the artifact nodes owning the given sections as 'stale'."""
    node_ids_seen: Set[UUID] = set()
    for sid in section_ids:
        sec = db.query(ArtifactSection).get(sid)
        if sec and sec.artifact_node_id not in node_ids_seen:
            node_ids_seen.add(sec.artifact_node_id)
            node = db.query(ArtifactNode).get(sec.artifact_node_id)
            if node:
                node.status = "stale"
    db.commit()


def mark_node_fresh(node_id: UUID, db: Session) -> None:
    """Mark an artifact node as 'fresh' after successful regeneration."""
    node = db.query(ArtifactNode).get(node_id)
    if node:
        node.status = "fresh"
        db.commit()
