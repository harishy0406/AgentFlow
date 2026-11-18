"""
Phase 21: Cloud FinOps & Multi-Cloud Infrastructure Cost Estimator Engine

Deterministically analyzes a project's SDD, DB_SCHEMA, and API_SPEC artifacts
to produce itemized monthly/annual cloud TCO estimates across AWS, GCP, and Azure
for Startup, Growth, and Enterprise deployment tiers, along with tailored FinOps
cost-optimization recommendations.
"""

import re
from datetime import datetime, timezone
from typing import Dict, Any, List
from uuid import UUID
from sqlalchemy.orm import Session

try:
    from ..models import Project
except ImportError:
    from app.models import Project


TIER_MULTIPLIERS: Dict[str, Dict[str, Any]] = {
    "startup": {
        "label": "Startup (MVP / Single-AZ)",
        "compute_factor": 0.45,
        "db_factor": 0.40,
        "cache_factor": 0.35,
        "network_factor": 0.50,
        "obs_factor": 0.40,
        "reserved_discount": 0.20,
        "estimated_rps": "Up to 250 RPS",
    },
    "growth": {
        "label": "Growth (Production Multi-AZ)",
        "compute_factor": 1.0,
        "db_factor": 1.0,
        "cache_factor": 1.0,
        "network_factor": 1.0,
        "obs_factor": 1.0,
        "reserved_discount": 0.28,
        "estimated_rps": "Up to 3,500 RPS",
    },
    "enterprise": {
        "label": "Enterprise (HA Active-Active)",
        "compute_factor": 2.6,
        "db_factor": 2.8,
        "cache_factor": 2.4,
        "network_factor": 2.2,
        "obs_factor": 2.5,
        "reserved_discount": 0.36,
        "estimated_rps": "15,000+ RPS",
    },
}


def detect_infrastructure_signals(sdd_text: str, db_text: str, api_text: str) -> Dict[str, Any]:
    """
    Statically inspects project artifacts to extract infrastructure sizing signals.
    """
    combined = f"{sdd_text}\n{db_text}\n{api_text}".lower()

    tables = re.findall(r"create\s+table\s+(?:if\s+not\s+exists\s+)?([a-zA-Z0-9_]+)", db_text, re.IGNORECASE)
    endpoints = re.findall(r"\b(?:GET|POST|PUT|DELETE|PATCH)\s+/[a-zA-Z0-9_{}/-]+", api_text, re.IGNORECASE)

    has_cache = bool(re.search(r"\b(redis|cache|memcached|redlock|elasticache)\b", combined))
    has_queue = bool(re.search(r"\b(kafka|rabbitmq|sqs|pubsub|celery|eventbridge|queue|webhook)\b", combined))
    has_realtime = bool(re.search(r"\b(websocket|webrtc|livekit|socket\.io|sse|streaming)\b", combined))
    has_ai_workload = bool(re.search(r"\b(pgvector|vector|embedding|llm|openai|claude|gpu|inference)\b", combined))
    has_compliance = bool(re.search(r"\b(hipaa|pci-dss|pci|soc2|upi|npci|escrow|fintech|audit_log)\b", combined))

    return {
        "tables_count": max(len(set(t.lower() for t in tables)), 3),
        "endpoints_count": max(len(set(e.upper() for e in endpoints)), 5),
        "has_cache": has_cache,
        "has_queue": has_queue,
        "has_realtime": has_realtime,
        "has_ai_workload": has_ai_workload,
        "has_compliance": has_compliance,
    }


def _build_cloud_breakdown(
    provider: str,
    signals: Dict[str, Any],
    tier_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Builds an itemized monthly cost table for a specific cloud provider (AWS, GCP, Azure).
    """
    tables = signals["tables_count"]
    endpoints = signals["endpoints_count"]

    # Base growth-tier monthly rates (USD) calibrated by cloud provider
    provider_profiles = {
        "AWS": {
            "compute_service": "Amazon ECS Fargate / EKS",
            "compute_base": 145.0,
            "db_service": "Amazon RDS PostgreSQL (Multi-AZ)",
            "db_base": 135.0,
            "cache_service": "Amazon ElastiCache (Redis 7)",
            "cache_base": 68.0,
            "queue_service": "Amazon SQS / MSK Serverless",
            "queue_base": 52.0,
            "network_service": "ALB + CloudFront CDN + NAT",
            "network_base": 58.0,
            "obs_service": "CloudWatch + AWS X-Ray",
            "obs_base": 42.0,
            "compliance_service": "AWS KMS + WAF + CloudTrail",
            "compliance_base": 55.0,
        },
        "GCP": {
            "compute_service": "Google Cloud Run / GKE Autopilot",
            "compute_base": 128.0,
            "db_service": "Cloud SQL for PostgreSQL (HA)",
            "db_base": 124.0,
            "cache_service": "Memorystore for Redis",
            "cache_base": 62.0,
            "queue_service": "Cloud Pub/Sub + Cloud Tasks",
            "queue_base": 44.0,
            "network_service": "Cloud Load Balancing + Cloud CDN",
            "network_base": 52.0,
            "obs_service": "Cloud Monitoring + Cloud Trace",
            "obs_base": 36.0,
            "compliance_service": "Cloud KMS + Cloud Armor",
            "compliance_base": 48.0,
        },
        "Azure": {
            "compute_service": "Azure Container Apps / AKS",
            "compute_base": 138.0,
            "db_service": "Azure Database for PostgreSQL Flexible",
            "db_base": 130.0,
            "cache_service": "Azure Cache for Redis",
            "cache_base": 66.0,
            "queue_service": "Azure Service Bus / Event Hubs",
            "queue_base": 48.0,
            "network_service": "Azure Front Door + App Gateway",
            "network_base": 55.0,
            "obs_service": "Azure Monitor + App Insights",
            "obs_base": 40.0,
            "compliance_service": "Azure Key Vault + Defender",
            "compliance_base": 52.0,
        },
    }

    prof = provider_profiles[provider]

    # Complexity modifiers derived from actual artifact structure
    api_complexity_mod = 1.0 + min(endpoints, 40) * 0.015
    db_complexity_mod = 1.0 + min(tables, 30) * 0.02
    realtime_add = 45.0 if signals["has_realtime"] else 0.0
    ai_add = 85.0 if signals["has_ai_workload"] else 0.0

    items: List[Dict[str, Any]] = [
        {
            "category": "Compute",
            "service": prof["compute_service"],
            "monthly_usd": round((prof["compute_base"] * api_complexity_mod + realtime_add + ai_add) * tier_cfg["compute_factor"], 2),
            "notes": f"Sized for {endpoints} endpoints" + (" + real-time/AI workers" if (signals["has_realtime"] or signals["has_ai_workload"]) else ""),
        },
        {
            "category": "Database",
            "service": prof["db_service"],
            "monthly_usd": round(prof["db_base"] * db_complexity_mod * tier_cfg["db_factor"], 2),
            "notes": f"Relational storage & automated backups for {tables} tables",
        },
        {
            "category": "Networking & CDN",
            "service": prof["network_service"],
            "monthly_usd": round(prof["network_base"] * tier_cfg["network_factor"], 2),
            "notes": "TLS termination, edge caching, and egress allowance",
        },
        {
            "category": "Observability",
            "service": prof["obs_service"],
            "monthly_usd": round(prof["obs_base"] * tier_cfg["obs_factor"], 2),
            "notes": "OpenTelemetry traces, structured logs, and golden-signal alerts",
        },
    ]

    if signals["has_cache"] or tier_cfg["cache_factor"] >= 1.0:
        items.append({
            "category": "Caching",
            "service": prof["cache_service"],
            "monthly_usd": round(prof["cache_base"] * tier_cfg["cache_factor"], 2),
            "notes": "Sub-millisecond hot-path cache and distributed locks",
        })

    if signals["has_queue"]:
        items.append({
            "category": "Messaging & Events",
            "service": prof["queue_service"],
            "monthly_usd": round(prof["queue_base"] * tier_cfg["network_factor"], 2),
            "notes": "Async job dispatch, CloudEvents delivery, and DLQ handling",
        })

    if signals["has_compliance"]:
        items.append({
            "category": "Security & Compliance",
            "service": prof["compliance_service"],
            "monthly_usd": round(prof["compliance_base"] * tier_cfg["obs_factor"], 2),
            "notes": "Envelope KMS encryption, WAF rules, and immutable audit logs",
        })

    monthly_total = round(sum(i["monthly_usd"] for i in items), 2)
    annual_on_demand = round(monthly_total * 12, 2)
    discount = tier_cfg["reserved_discount"]
    annual_reserved = round(annual_on_demand * (1.0 - discount), 2)
    annual_savings = round(annual_on_demand - annual_reserved, 2)

    return {
        "provider": provider,
        "monthly_total_usd": monthly_total,
        "annual_on_demand_usd": annual_on_demand,
        "annual_reserved_usd": annual_reserved,
        "annual_savings_usd": annual_savings,
        "reserved_discount_pct": int(discount * 100),
        "line_items": items,
    }


def _generate_finops_recommendations(signals: Dict[str, Any], tier: str) -> List[Dict[str, str]]:
    recs = [
        {
            "title": "Adopt 1-Year Compute Savings Plans / CUDs",
            "impact": "High (20-36% savings)",
            "detail": "Lock in baseline container & database capacity after 30 days of production telemetry to eliminate on-demand premiums.",
        },
        {
            "title": "Enable ARM64 (Graviton / Tau) Container Builds",
            "impact": "Medium (15-20% compute savings)",
            "detail": "Multi-arch Docker builds targeting linux/arm64 deliver superior price-performance for FastAPI and Node.js workloads.",
        },
    ]

    if signals["has_cache"]:
        recs.append({
            "title": "Tune Redis TTL & Eviction Policies",
            "impact": "Medium (10-15% DB offload)",
            "detail": "Use allkeys-lru eviction and targeted read-through TTLs to avoid over-provisioning primary PostgreSQL IOPS.",
        })

    if signals["has_ai_workload"]:
        recs.append({
            "title": "Implement Semantic Prompt Caching & Tiered Model Routing",
            "impact": "High (40-60% inference savings)",
            "detail": "Route deterministic classification and extraction tasks to fast small models (Groq / Flash) while reserving frontier models for synthesis.",
        })

    if tier == "enterprise":
        recs.append({
            "title": "Schedule Non-Prod Environment Auto-Hibernate",
            "impact": "Medium (Up to 65% staging savings)",
            "detail": "Scale staging and QA Kubernetes namespaces to zero replicas outside engineering working hours.",
        })

    return recs


def estimate_project_cloud_costs(
    project_id: UUID,
    db: Session,
    tier: str = "growth",
) -> Dict[str, Any]:
    """
    Computes a full multi-cloud FinOps cost estimate for a given project.
    """
    normalized_tier = (tier or "growth").lower().strip()
    if normalized_tier not in TIER_MULTIPLIERS:
        normalized_tier = "growth"

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    def _artifact_text(artifact_type: str) -> str:
        node = next((n for n in project.artifact_nodes if n.artifact_type == artifact_type), None)
        if not node or not node.sections:
            return ""
        return "\n\n".join(s.content for s in node.sections)

    sdd_text = _artifact_text("SDD")
    db_text = _artifact_text("DB_SCHEMA")
    api_text = _artifact_text("API_SPEC")

    signals = detect_infrastructure_signals(sdd_text, db_text, api_text)
    tier_cfg = TIER_MULTIPLIERS[normalized_tier]

    providers = [
        _build_cloud_breakdown("AWS", signals, tier_cfg),
        _build_cloud_breakdown("GCP", signals, tier_cfg),
        _build_cloud_breakdown("Azure", signals, tier_cfg),
    ]

    cheapest = min(providers, key=lambda p: p["monthly_total_usd"])

    return {
        "project_id": str(project.id),
        "project_name": project.name,
        "tier": normalized_tier,
        "tier_label": tier_cfg["label"],
        "estimated_rps": tier_cfg["estimated_rps"],
        "detected_signals": signals,
        "recommended_provider": cheapest["provider"],
        "lowest_monthly_usd": cheapest["monthly_total_usd"],
        "providers": providers,
        "finops_recommendations": _generate_finops_recommendations(signals, normalized_tier),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
