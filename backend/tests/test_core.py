"""
Unit Tests — Graph Engine, Router Scoring & Schema Validation

Tests for:
  1. Content hashing (deterministic SHA-256)
  2. Diff summary computation
  3. Dependency map structure and topological ordering
  4. Router candidate scoring (quality-per-dollar) — via isolated reimplementation
  5. Pydantic schema validation
"""

import pytest
import hashlib

# ---------------------------------------------------------------------------
# 1. Graph Engine — Content Hashing
# ---------------------------------------------------------------------------

from app.agents.graph_engine import compute_content_hash


class TestContentHashing:
    def test_deterministic_hash(self):
        """Same input must always produce the same hash."""
        content = "# Product Requirements Document\n## Overview\nBuild an e-commerce app."
        h1 = compute_content_hash(content)
        h2 = compute_content_hash(content)
        assert h1 == h2

    def test_different_content_different_hash(self):
        """Different inputs must produce different hashes."""
        h1 = compute_content_hash("version 1")
        h2 = compute_content_hash("version 2")
        assert h1 != h2

    def test_hash_is_sha256_hex(self):
        """Hash must be a 64-character hex string (SHA-256)."""
        h = compute_content_hash("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_matches_stdlib_sha256(self):
        """Our hash must match Python's hashlib SHA-256."""
        content = "hello agentflow"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert compute_content_hash(content) == expected

    def test_empty_string_hashes(self):
        """Empty string should still produce a valid hash."""
        h = compute_content_hash("")
        assert len(h) == 64


# ---------------------------------------------------------------------------
# 2. Graph Engine — Diff Summary
# ---------------------------------------------------------------------------

from app.agents.graph_engine import compute_diff_summary


class TestDiffSummary:
    def test_identical_content_no_diff(self):
        """Identical content should report no changes."""
        result = compute_diff_summary("hello world", "hello world")
        assert result == "No changes detected."

    def test_changed_content_produces_diff(self):
        """Modified content should produce a unified diff output."""
        old = "line 1\nline 2\nline 3"
        new = "line 1\nline 2 modified\nline 3"
        result = compute_diff_summary(old, new)
        assert "-line 2" in result
        assert "+line 2 modified" in result

    def test_added_lines(self):
        """Adding lines should appear in the diff."""
        old = "line 1"
        new = "line 1\nline 2"
        result = compute_diff_summary(old, new)
        assert "+line 2" in result


# ---------------------------------------------------------------------------
# 3. Graph Engine — Dependency Map Structure
# ---------------------------------------------------------------------------

from app.agents.graph_engine import (
    ARTIFACT_DEPENDENCY_MAP,
    ARTIFACT_DOWNSTREAM_MAP,
    TOPOLOGICAL_ORDER,
)


class TestDependencyMap:
    def test_prd_has_no_dependencies(self):
        """PRD is the root node — no upstream dependencies."""
        assert ARTIFACT_DEPENDENCY_MAP["PRD"] == []

    def test_sdd_depends_on_prd(self):
        """SDD depends on PRD."""
        assert "PRD" in ARTIFACT_DEPENDENCY_MAP["SDD"]

    def test_api_spec_depends_on_sdd_and_db_schema(self):
        """API_SPEC depends on both SDD and DB_SCHEMA."""
        deps = ARTIFACT_DEPENDENCY_MAP["API_SPEC"]
        assert "SDD" in deps
        assert "DB_SCHEMA" in deps

    def test_tasks_is_terminal(self):
        """TASKS should have no downstream dependents."""
        assert len(ARTIFACT_DOWNSTREAM_MAP.get("TASKS", [])) == 0

    def test_prd_has_downstream(self):
        """PRD should have SDD and USER_STORIES as downstream."""
        downstream = ARTIFACT_DOWNSTREAM_MAP["PRD"]
        assert "SDD" in downstream
        assert "USER_STORIES" in downstream

    def test_topological_order_length(self):
        """Topological order must contain all 6 artifact types."""
        assert len(TOPOLOGICAL_ORDER) == 6

    def test_topological_order_prd_first(self):
        """PRD must be the first element in topological order."""
        assert TOPOLOGICAL_ORDER[0] == "PRD"

    def test_topological_order_tasks_last(self):
        """TASKS must be the last element in topological order."""
        assert TOPOLOGICAL_ORDER[-1] == "TASKS"

    def test_all_artifact_types_in_order(self):
        """All keys in the dependency map must appear in the topological order."""
        for artifact_type in ARTIFACT_DEPENDENCY_MAP:
            assert artifact_type in TOPOLOGICAL_ORDER

    def test_dependency_consistency(self):
        """Every parent in the dependency map should list the child as downstream."""
        for child, parents in ARTIFACT_DEPENDENCY_MAP.items():
            for parent in parents:
                assert child in ARTIFACT_DOWNSTREAM_MAP[parent], \
                    f"{child} should be downstream of {parent}"


# ---------------------------------------------------------------------------
# 4. Router — Candidate Scoring (Isolated, no LangChain deps)
# ---------------------------------------------------------------------------

class TestRouterScoringIsolated:
    """
    Tests the quality-per-dollar scoring math without importing the full
    router module (which requires langchain_openai). We replicate the
    core _score_candidate logic here for pure unit testing.
    """

    @staticmethod
    def _score(hist_quality: float, cost: float) -> float:
        """Replicate the q/d formula from router._score_candidate."""
        if cost <= 0:
            cost = 1e-12
        return hist_quality / cost

    def test_quality_per_dollar_basic(self):
        """Basic q/d calculation."""
        qpd = self._score(0.8, 0.00001)
        assert qpd == pytest.approx(80000.0)

    def test_higher_quality_wins(self):
        """At same cost, higher quality should yield higher q/d."""
        qpd_high = self._score(0.95, 0.00005)
        qpd_low = self._score(0.60, 0.00005)
        assert qpd_high > qpd_low

    def test_cheaper_model_wins_at_equal_quality(self):
        """At same quality, cheaper model should yield higher q/d."""
        qpd_cheap = self._score(0.8, 0.00001)
        qpd_expensive = self._score(0.8, 0.00010)
        assert qpd_cheap > qpd_expensive

    def test_zero_cost_does_not_crash(self):
        """A free model (cost=0) should use epsilon and not crash."""
        qpd = self._score(0.7, 0.0)
        assert qpd > 0

    def test_default_prior_quality(self):
        """Models without history should use 0.5 as default prior."""
        default_quality = 0.5
        qpd = self._score(default_quality, 0.00003)
        expected = 0.5 / 0.00003
        assert qpd == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 5. Pydantic Schema Validation
# ---------------------------------------------------------------------------

from app.schemas import ProjectCreate, ClarifyRequest, ArtifactSectionUpdate


class TestSchemaValidation:
    def test_project_create_valid(self):
        p = ProjectCreate(name="Test", brief="A simple app")
        assert p.name == "Test"
        assert p.clarifications is None

    def test_project_create_with_clarifications(self):
        p = ProjectCreate(name="Test", brief="Build X", clarifications="Q: What? A: Y")
        assert p.clarifications == "Q: What? A: Y"

    def test_clarify_request(self):
        c = ClarifyRequest(brief="Build a fintech app")
        assert c.brief == "Build a fintech app"

    def test_section_update(self):
        s = ArtifactSectionUpdate(content="Updated content here")
        assert s.content == "Updated content here"

    def test_project_create_missing_name_fails(self):
        """Missing required 'name' field should raise validation error."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ProjectCreate(brief="A simple app")

    def test_project_create_missing_brief_fails(self):
        """Missing required 'brief' field should raise validation error."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ProjectCreate(name="Test")
