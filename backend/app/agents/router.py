"""
Quality-Signal Router (Decision Engine) — Phase 3

Routes each artifact generation to the most cost-effective capable model
based on:
  1. Historical quality-signal performance per model per artifact type
  2. Cost per token for the provider
  3. A quality-per-dollar ranking

The router is provider-agnostic: adding a new LLM provider only requires
registering it in the ProviderRegistry.
"""

from typing import Dict, List, Optional
from uuid import UUID
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import func
from langchain_core.language_models.chat_models import BaseChatModel

from ..models import GenerationLog
from .provider_registry import PROVIDER_REGISTRY, ModelEntry


@dataclass
class CandidateScore:
    """Intermediate scoring result for a model candidate."""
    model_entry: ModelEntry
    historical_quality: float      # avg quality signal from past generations
    cost_per_token: float          # average of input/output cost
    quality_per_dollar: float      # historical_quality / cost_per_token
    sample_count: int              # how many past data points we have


@dataclass
class RoutingDecision:
    """The router's final decision, logged for observability."""
    artifact_type: str
    chosen_provider: str
    chosen_model: str
    predicted_quality_signal: float
    estimated_cost_usd: float
    rationale: str

    def to_dict(self) -> Dict:
        return {
            "artifact_type": self.artifact_type,
            "chosen_provider": self.chosen_provider,
            "chosen_model": self.chosen_model,
            "predicted_quality_signal": self.predicted_quality_signal,
            "estimated_cost_usd": self.estimated_cost_usd,
            "rationale": self.rationale,
        }


# ---------------------------------------------------------------------------
# Historical score lookups
# ---------------------------------------------------------------------------

def _get_historical_scores(
    artifact_type: str,
    db: Session,
) -> Dict[str, float]:
    """
    Query generation_logs to compute the average quality_signal_score
    for each (provider, model) pair that has generated this artifact type.

    Returns {f"{provider}/{model}": avg_score, ...}
    """
    from ..models import ArtifactNode

    # Join generation_logs with artifact_nodes to filter by artifact_type
    rows = (
        db.query(
            GenerationLog.provider,
            GenerationLog.model,
            func.avg(ArtifactNode.quality_signal_score).label("avg_quality"),
            func.count(GenerationLog.id).label("sample_count"),
        )
        .join(ArtifactNode, GenerationLog.artifact_node_id == ArtifactNode.id)
        .filter(
            ArtifactNode.artifact_type == artifact_type,
            ArtifactNode.quality_signal_score.isnot(None),
        )
        .group_by(GenerationLog.provider, GenerationLog.model)
        .all()
    )

    scores = {}
    for row in rows:
        key = f"{row.provider}/{row.model}"
        scores[key] = float(row.avg_quality) if row.avg_quality else 0.5
    return scores


def _score_candidate(
    model: ModelEntry,
    artifact_type: str,
    historical_scores: Dict[str, float],
) -> CandidateScore:
    """
    Score a single model candidate for a given artifact type.

    Combines:
      - historical quality signal (default 0.5 if no data yet)
      - cost per token
    into a quality_per_dollar metric.
    """
    key = f"{model.provider}/{model.model_name}"
    hist_quality = historical_scores.get(key, 0.5)  # default prior
    cost = model.avg_cost_per_token

    # Avoid division by zero — treat free models as extremely cheap
    if cost <= 0:
        cost = 1e-12

    quality_per_dollar = hist_quality / cost

    # Count how many data points we have (for the rationale)
    sample_count = 1 if key in historical_scores else 0

    return CandidateScore(
        model_entry=model,
        historical_quality=hist_quality,
        cost_per_token=cost,
        quality_per_dollar=quality_per_dollar,
        sample_count=sample_count,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def route(
    artifact_type: str,
    context_size: int,
    db: Session,
) -> RoutingDecision:
    """
    Select the best model for generating the given artifact type.

    Algorithm:
      1. Get all eligible models from the ProviderRegistry
      2. Fetch historical quality scores from generation_logs
      3. Score each candidate on quality_per_dollar
      4. Pick the best
      5. Return a RoutingDecision (logged by the caller)
    """
    candidates = PROVIDER_REGISTRY.models_for(artifact_type)

    if not candidates:
        # Fallback: no providers available — use a hardcoded default
        return RoutingDecision(
            artifact_type=artifact_type,
            chosen_provider="openai",
            chosen_model="gpt-4o-mini",
            predicted_quality_signal=0.5,
            estimated_cost_usd=0.0,
            rationale="No providers available; using hardcoded fallback.",
        )

    # Filter by context size
    candidates = [c for c in candidates if c.max_context_tokens >= context_size]
    if not candidates:
        # All models too small — use the largest available
        candidates = PROVIDER_REGISTRY.models_for(artifact_type)
        candidates.sort(key=lambda m: m.max_context_tokens, reverse=True)
        candidates = [candidates[0]]

    historical_scores = _get_historical_scores(artifact_type, db)

    scored = [
        _score_candidate(m, artifact_type, historical_scores)
        for m in candidates
    ]

    # Pick the candidate with the highest quality_per_dollar
    best = max(scored, key=lambda s: s.quality_per_dollar)

    # Estimate cost: rough heuristic based on context_size as proxy for
    # total tokens (input + output ≈ 2x context)
    estimated_tokens = context_size * 2
    estimated_cost = estimated_tokens * best.cost_per_token

    # Build rationale
    if best.sample_count > 0:
        rationale = (
            f"Selected {best.model_entry.provider}/{best.model_entry.model_name} "
            f"based on historical quality {best.historical_quality:.2f} "
            f"and cost ${best.cost_per_token*1_000_000:.2f}/M tokens "
            f"(quality/$ = {best.quality_per_dollar:.2e}, "
            f"{best.sample_count} historical samples)."
        )
    else:
        rationale = (
            f"Selected {best.model_entry.provider}/{best.model_entry.model_name} "
            f"using default prior (no historical data for {artifact_type}). "
            f"Cost: ${best.cost_per_token*1_000_000:.2f}/M tokens."
        )

    return RoutingDecision(
        artifact_type=artifact_type,
        chosen_provider=best.model_entry.provider,
        chosen_model=best.model_entry.model_name,
        predicted_quality_signal=best.historical_quality,
        estimated_cost_usd=estimated_cost,
        rationale=rationale,
    )


def get_chat_model_for_artifact(
    artifact_type: str,
    context_size: int,
    db: Session,
) -> tuple[BaseChatModel, RoutingDecision]:
    """
    Convenience wrapper: route and instantiate the ChatModel in one call.
    Returns (chat_model, routing_decision).
    """
    decision = route(artifact_type, context_size, db)
    chat_model = PROVIDER_REGISTRY.get_chat_model(
        decision.chosen_provider, decision.chosen_model
    )
    return chat_model, decision
