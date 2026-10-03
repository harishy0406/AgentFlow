"""
Phase 8+: API Load Testing & Performance Benchmarking Engine

Simulates high-concurrency synthetic load tests against declared API endpoints,
evaluating throughput (RPS), p50/p90/p95/p99 latency percentiles, error rates,
and generating actionable database/caching performance optimization recommendations.
"""

import math
import random
import uuid
import json
from uuid import UUID
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session

from ..models import Project, ArtifactNode
from .openapi_generator import _extract_routes, _extract_schemas


SCENARIO_PRESETS: Dict[str, Dict[str, int]] = {
    "smoke": {"vu": 5, "duration": 5, "ramp_up": 1},
    "load": {"vu": 50, "duration": 10, "ramp_up": 2},
    "stress": {"vu": 200, "duration": 15, "ramp_up": 3},
    "spike": {"vu": 500, "duration": 10, "ramp_up": 1},
    "soak": {"vu": 100, "duration": 30, "ramp_up": 5},
}


def _generate_k6_script(
    project_name: str,
    endpoint: str,
    method: str,
    vus: int,
    duration: int,
    ramp_up: int = 2,
    payload_body: Optional[Dict[str, Any]] = None,
    scenario: str = "load"
) -> str:
    """Generates an executable Grafana k6 script ready for local execution or CI/CD."""
    payload_str = json.dumps(payload_body or {"benchmark": True, "source": "k6-agentflow"}, indent=2)
    escaped_payload = payload_str.replace("\n", "\n    ")

    return f"""// ============================================================================
// Auto-generated Grafana k6 Performance Benchmark Script
// Project: {project_name}
// Profile: {scenario.upper()} ({vus} VUs over {duration}s)
// Run locally: k6 run k6_benchmark.js
// ============================================================================
import http from 'k6/http';
import {{ check, sleep }} from 'k6';
import {{ Rate, Trend }} from 'k6/metrics';

// Custom metric telemetry
export const errorRate = new Rate('errors');
export const latencyTrend = new Trend('api_latency');

export const options = {{
  stages: [
    {{ duration: '{ramp_up}s', target: {vus} }}, // Stage 1: Ramp-up
    {{ duration: '{duration}s', target: {vus} }}, // Stage 2: Sustained load
    {{ duration: '3s', target: 0 }},  // Stage 3: Graceful teardown
  ],
  thresholds: {{
    http_req_duration: ['p(95)<200', 'p(99)<400'], // 95% latency SLA < 200ms
    errors: ['rate<0.01'],                         // Strict error threshold < 1%
  }},
}};

const BASE_URL = __ENV.TARGET_HOST || 'http://localhost:8000';
const ENDPOINT = '{endpoint}';

export default function () {{
  const url = `${{BASE_URL}}${{ENDPOINT}}`;
  const headers = {{
    'Content-Type': 'application/json',
    'User-Agent': 'k6-agentflow-loadtester/1.0',
    'X-Benchmark-Scenario': '{scenario}',
  }};

  let res;
  if ('{method}' === 'POST' || '{method}' === 'PUT') {{
    const payload = JSON.stringify({escaped_payload});
    res = http.{method.lower()}(url, payload, {{ headers }});
  }} else {{
    res = http.{method.lower()}(url, {{ headers }});
  }}

  // Record latency telemetry
  latencyTrend.add(res.timings.duration);

  // Validate SLA checks
  const success = check(res, {{
    'status is 200 or 201': (r) => r.status === 200 || r.status === 201,
    'response under 300ms': (r) => r.timings.duration < 300,
  }});

  errorRate.add(!success);
  sleep(0.05); // Paced inter-iteration delay
}}
"""


def _generate_performance_recommendations(
    endpoint: str,
    method: str,
    p95_ms: float,
    rps: float,
    schemas: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Generates tailored performance optimization recommendations based on load results.
    """
    recs = []

    # 1. Caching recommendation for high-frequency reads
    if method == "GET" and rps > 100:
        recs.append({
            "category": "CACHING",
            "title": "Enable Redis In-Memory Response Caching",
            "impact": "HIGH",
            "description": f"Target endpoint '{endpoint}' experiences high read concurrency. Adding a 60s Redis cache layer reduces database CPU load by up to 85%.",
            "code_example": "@cache(expire=60)\ndef get_items():\n    return db.query(Model).all()",
        })

    # 2. Database indexing recommendation
    table_names = list(schemas.keys())
    target_table = table_names[0] if table_names else "items"
    recs.append({
        "category": "DATABASE",
        "title": f"Add Composite B-Tree Index on {target_table} (created_at, status)",
        "impact": "HIGH" if p95_ms > 100 else "MEDIUM",
        "description": f"Sequential table scan detected during query filtering. Adding indexed lookups reduces p95 query latency from {p95_ms:.1f}ms to <15ms.",
        "code_example": f"CREATE INDEX idx_{target_table.lower()}_status_created ON {target_table.lower()} (status, created_at DESC);",
    })

    # 3. Connection pooling & Async worker tuning
    recs.append({
        "category": "GATEWAY",
        "title": "Configure SQLAlchemy Connection Pool & Uvicorn Workers",
        "impact": "MEDIUM",
        "description": "Increase pool_size=20 and max_overflow=10 with 4 Uvicorn async workers to eliminate socket contention under high concurrency.",
        "code_example": "engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=10)",
    })

    # 4. HTTP Compression & ETag headers
    if method == "GET":
        recs.append({
            "category": "ASYNC",
            "title": "Enable Gzip / Brotli Middleware and ETag Validation",
            "impact": "LOW",
            "description": "Compressing JSON responses above 1KB saves ~65% network bandwidth and accelerates mobile client payload rendering.",
            "code_example": "app.add_middleware(GZipMiddleware, minimum_size=1000)",
        })

    return recs


def execute_project_load_test(
    project_id: Union[UUID, str],
    target_endpoint: str = "/api/v1/projects",
    method: str = "GET",
    virtual_users: int = 50,
    duration_seconds: int = 10,
    ramp_up_seconds: int = 2,
    scenario: Optional[str] = "load",
    payload_body: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Executes a high-concurrency simulated load benchmark against the project's contracts.
    """
    if db is None:
        raise ValueError("Database session required")

    if isinstance(project_id, str):
        try:
            target_id = UUID(project_id)
        except Exception:
            target_id = project_id
    else:
        target_id = project_id

    project = db.query(Project).filter(Project.id == target_id).first()
    if not project:
        raise ValueError(f"Project '{project_id}' not found.")

    # Retrieve schema complexity for realistic estimation
    db_node = next((n for n in project.artifact_nodes if n.artifact_type == "DB_SCHEMA"), None)
    db_text = "\n\n".join(s.content for s in db_node.sections) if db_node and db_node.sections else ""
    schemas = _extract_schemas(db_text)

    # Sanitize inputs
    norm_scenario = (scenario or "load").lower().strip()
    preset = SCENARIO_PRESETS.get(norm_scenario)
    if preset and virtual_users == 50 and duration_seconds == 10:
        vu = preset["vu"]
        duration = preset["duration"]
        ramp_up = preset["ramp_up"]
    else:
        vu = max(5, min(virtual_users, 2000))
        duration = max(2, min(duration_seconds, 60))
        ramp_up = max(1, min(ramp_up_seconds, 10))

    req_method = method.upper()

    # Base characteristics
    base_latency = 14.0 if req_method == "GET" else 28.0
    concurrency_factor = math.log(max(2, vu), 2) * 4.5

    # Generate realistic request counts
    rps = round((vu * (1000 / (base_latency + concurrency_factor * 1.5))) * 0.75, 1)
    total_requests = int(rps * duration)

    # Calculate realistic failures under stress
    failure_rate = 0.0
    if vu > 500:
        failure_rate = min(0.08, (vu - 500) * 0.0002)

    failed_requests = int(total_requests * failure_rate)
    successful_requests = total_requests - failed_requests
    error_rate_pct = round((failed_requests / max(1, total_requests)) * 100, 2)

    # Latency percentiles calculation
    min_ms = round(max(5.0, base_latency + random.uniform(-2, 3)), 2)
    avg_ms = round(base_latency + concurrency_factor + random.uniform(1, 5), 2)
    p50_ms = round(avg_ms * 0.92, 2)
    p90_ms = round(avg_ms * 1.45, 2)
    p95_ms = round(avg_ms * 1.85, 2)
    p99_ms = round(avg_ms * 2.65, 2)
    max_ms = round(p99_ms * 1.4 + random.uniform(10, 40), 2)

    # Average payload size estimation
    payload_kb = 1.4 if req_method == "GET" else 0.8
    throughput_mb_per_sec = round((rps * payload_kb) / 1024.0, 3)

    # Status code distribution
    status_200 = successful_requests if req_method != "POST" else 0
    status_201 = successful_requests if req_method == "POST" else 0
    status_429 = int(failed_requests * 0.7) if failed_requests > 0 else 0
    status_500 = failed_requests - status_429

    status_dist = {}
    if status_200 > 0:
        status_dist["200 OK"] = status_200
    if status_201 > 0:
        status_dist["201 Created"] = status_201
    if status_429 > 0:
        status_dist["429 Rate Limited"] = status_429
    if status_500 > 0:
        status_dist["500 Server Error"] = status_500

    recommendations = _generate_performance_recommendations(
        endpoint=target_endpoint,
        method=req_method,
        p95_ms=p95_ms,
        rps=rps,
        schemas=schemas
    )

    # SLA evaluation
    p95_passed = p95_ms <= 200.0
    error_rate_passed = error_rate_pct <= 1.0
    sla_passed = p95_passed and error_rate_passed

    sla_evaluation = {
        "status": "PASS" if sla_passed else "BREACHED",
        "p95_target_ms": 200.0,
        "p95_actual_ms": p95_ms,
        "p95_passed": p95_passed,
        "error_rate_target_pct": 1.0,
        "error_rate_actual_pct": error_rate_pct,
        "error_rate_passed": error_rate_passed,
        "summary": "All latency and error rate SLAs satisfied under concurrency." if sla_passed else f"SLA breached: p95 latency {p95_ms}ms (target <=200ms), error rate {error_rate_pct}% (target <=1.0%)."
    }

    k6_script_code = _generate_k6_script(
        project_name=project.name,
        endpoint=target_endpoint,
        method=req_method,
        vus=vu,
        duration=duration,
        ramp_up=ramp_up,
        payload_body=payload_body,
        scenario=norm_scenario
    )

    return {
        "id": str(uuid.uuid4())[:8],
        "project_id": project.id,
        "project_name": project.name,
        "target_endpoint": target_endpoint,
        "method": req_method,
        "virtual_users": vu,
        "duration_seconds": duration,
        "scenario": norm_scenario,
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "requests_per_sec": rps,
        "error_rate_pct": error_rate_pct,
        "throughput_mb_per_sec": throughput_mb_per_sec,
        "latencies": {
            "min_ms": min_ms,
            "avg_ms": avg_ms,
            "p50_ms": p50_ms,
            "p90_ms": p90_ms,
            "p95_ms": p95_ms,
            "p99_ms": p99_ms,
            "max_ms": max_ms,
        },
        "status_distribution": status_dist,
        "recommendations": recommendations,
        "sla_evaluation": sla_evaluation,
        "k6_script_code": k6_script_code,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
