"""
Phase 10: OpenTelemetry Distributed Tracing & APM Metrics Instrumentation Engine

Generates production-grade OpenTelemetry collector configurations,
Prometheus golden signal scrape targets, Grafana dashboard definitions,
and Python / FastAPI instrumentation middleware.
"""

from uuid import UUID
from typing import Dict, Any, List, Union
from sqlalchemy.orm import Session

from ..models import Project
from .scaffolder import sanitize_project_slug


def _generate_metrics_catalog(project_slug: str) -> List[Dict[str, Any]]:
    """Generates Google SRE Golden Signals metrics catalog for the project."""
    return [
        {
            "name": f"{project_slug}_http_requests_total",
            "type": "COUNTER",
            "description": "Total count of HTTP requests processed by endpoint and HTTP status code.",
            "labels": ["method", "endpoint", "status"]
        },
        {
            "name": f"{project_slug}_http_request_duration_seconds",
            "type": "HISTOGRAM",
            "description": "Latency distribution of HTTP request lifecycles in seconds.",
            "labels": ["method", "endpoint"]
        },
        {
            "name": f"{project_slug}_active_in_flight_requests",
            "type": "GAUGE",
            "description": "Current number of concurrently executing HTTP requests.",
            "labels": ["method"]
        },
        {
            "name": f"{project_slug}_db_pool_connections_active",
            "type": "GAUGE",
            "description": "Active checked-out database connections in the SQLAlchemy connection pool.",
            "labels": ["pool_name"]
        },
        {
            "name": f"{project_slug}_db_query_duration_seconds",
            "type": "HISTOGRAM",
            "description": "Execution time distribution for relational database queries.",
            "labels": ["query_type", "table"]
        }
    ]


def _generate_otel_collector_config(project_slug: str) -> str:
    """Generates OpenTelemetry Collector configuration YAML."""
    return f"""# OpenTelemetry Collector Configuration for {project_slug}
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

  prometheus:
    config:
      scrape_configs:
        - job_name: '{project_slug}-api'
          scrape_interval: 10s
          static_configs:
            - targets: ['app:8000']

processors:
  batch:
    timeout: 1s
    send_batch_size: 256
  memory_limiter:
    check_interval: 2s
    limit_percentage: 80
    spike_limit_percentage: 20

exporters:
  prometheus:
    endpoint: 0.0.0.0:8889
    namespace: {project_slug}
    send_timestamps: true

  otlp/jaeger:
    endpoint: jaeger:4317
    tls:
      insecure: true

  logging:
    loglevel: warn

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/jaeger, logging]
    metrics:
      receivers: [otlp, prometheus]
      processors: [memory_limiter, batch]
      exporters: [prometheus, logging]
"""


def _generate_prometheus_config(project_slug: str) -> str:
    """Generates Prometheus scraping configuration."""
    return f"""global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: '{project_slug}-otel-collector'
    static_configs:
      - targets: ['otel-collector:8889']

  - job_name: '{project_slug}-fastapi-direct'
    metrics_path: '/metrics'
    static_configs:
      - targets: ['app:8000']
"""


def _generate_grafana_dashboard(project_name: str, project_slug: str) -> Dict[str, Any]:
    """Generates an importable Grafana Dashboard JSON definition with Golden Signal panels."""
    return {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "id": 1,
                "title": "Throughput — Requests / Sec (RPS)",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                "targets": [
                    {
                        "expr": f'sum(rate({project_slug}_http_requests_total[1m])) by (endpoint)',
                        "legendFormat": "{{endpoint}}",
                        "refId": "A"
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "unit": "reqps",
                        "color": {"mode": "palette-classic"}
                    }
                }
            },
            {
                "id": 2,
                "title": "Tail Latency Percentiles (p50, p95, p99)",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
                "targets": [
                    {
                        "expr": f'histogram_quantile(0.99, sum(rate({project_slug}_http_request_duration_seconds_bucket[5m])) by (le)) * 1000',
                        "legendFormat": "p99 Tail (ms)",
                        "refId": "p99"
                    },
                    {
                        "expr": f'histogram_quantile(0.95, sum(rate({project_slug}_http_request_duration_seconds_bucket[5m])) by (le)) * 1000',
                        "legendFormat": "p95 Target (ms)",
                        "refId": "p95"
                    },
                    {
                        "expr": f'histogram_quantile(0.50, sum(rate({project_slug}_http_request_duration_seconds_bucket[5m])) by (le)) * 1000',
                        "legendFormat": "p50 Median (ms)",
                        "refId": "p50"
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "unit": "ms",
                        "color": {"mode": "thresholds"}
                    }
                }
            },
            {
                "id": 3,
                "title": "HTTP 5xx Error Rate Spike (%)",
                "type": "stat",
                "gridPos": {"h": 6, "w": 8, "x": 0, "y": 8},
                "targets": [
                    {
                        "expr": f'sum(rate({project_slug}_http_requests_total{{status=~"5.."}}[5m])) / sum(rate({project_slug}_http_requests_total[5m])) * 100',
                        "legendFormat": "Error Rate",
                        "refId": "A"
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "unit": "percent",
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "yellow", "value": 1.0},
                                {"color": "red", "value": 5.0}
                            ]
                        }
                    }
                }
            },
            {
                "id": 4,
                "title": "Active In-Flight Concurrency",
                "type": "gauge",
                "gridPos": {"h": 6, "w": 8, "x": 8, "y": 8},
                "targets": [
                    {
                        "expr": f'sum({project_slug}_active_in_flight_requests)',
                        "legendFormat": "VUs Concurrent",
                        "refId": "A"
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "max": 500,
                        "color": {"mode": "continuous-GrYlRd"}
                    }
                }
            },
            {
                "id": 5,
                "title": "SQLAlchemy DB Pool Active Connections",
                "type": "timeseries",
                "gridPos": {"h": 6, "w": 8, "x": 16, "y": 8},
                "targets": [
                    {
                        "expr": f'{project_slug}_db_pool_connections_active',
                        "legendFormat": "Pool Connections",
                        "refId": "A"
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "color": {"fixedColor": "#38BDF8", "mode": "fixed"}
                    }
                }
            }
        ],
        "schemaVersion": 38,
        "style": "dark",
        "tags": ["agentflow", project_slug, "opentelemetry", "golden-signals"],
        "time": {"from": "now-30m", "to": "now"},
        "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m"]},
        "timezone": "browser",
        "title": f"{project_name} — APM & Golden Signals",
        "uid": f"apm-{project_slug}",
        "version": 1
    }


def _generate_fastapi_telemetry_middleware(project_slug: str) -> str:
    """Generates OpenTelemetry tracing middleware and Prometheus metric exporter for FastAPI."""
    return f'''"""
{project_slug.upper()} OpenTelemetry & Prometheus Middleware
Handles W3C TraceContext propagation, span creation, request latency histograms,
and exposes standard /metrics endpoint.
"""

import time
import uuid
from typing import Callable
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Golden Signals Prometheus Metrics
REQUESTS_TOTAL = Counter(
    "{project_slug}_http_requests_total",
    "Total HTTP requests handled",
    ["method", "endpoint", "status"]
)

REQUEST_DURATION = Histogram(
    "{project_slug}_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

ACTIVE_REQUESTS = Gauge(
    "{project_slug}_active_in_flight_requests",
    "Concurrent in-flight requests",
    ["method"]
)


class OpenTelemetryTracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract or generate W3C TraceContext ID
        traceparent = request.headers.get("traceparent")
        if not traceparent:
            trace_id = uuid.uuid4().hex
            span_id = uuid.uuid4().hex[:16]
            traceparent = f"00-{{trace_id}}-{{span_id}}-01"

        method = request.method
        endpoint = request.url.path

        ACTIVE_REQUESTS.labels(method=method).inc()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            status_code = 500
            raise exc from None
        finally:
            duration = time.perf_counter() - start_time
            ACTIVE_REQUESTS.labels(method=method).dec()

            # Record Prometheus metrics (filter out /metrics scrape noise)
            if endpoint != "/metrics":
                REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status=str(status_code)).inc()
                REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

        # Inject tracing metadata in response header for downstream client debugging
        response.headers["traceparent"] = traceparent
        response.headers["X-Response-Time-Ms"] = f"{{duration * 1000:0.2f}}"
        return response


def setup_telemetry(app: FastAPI):
    """Hooks OpenTelemetry tracing middleware and the /metrics endpoint into FastAPI app."""
    app.add_middleware(OpenTelemetryTracingMiddleware)

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
'''


def _generate_telemetry_docker_compose(project_slug: str) -> str:
    """Generates multi-container APM Docker Compose stack for Jaeger, Prometheus, and Grafana."""
    return f"""version: '3.8'

services:
  # OpenTelemetry Collector Contrib
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.98.0
    container_name: {project_slug}-otel-collector
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otel-collector-config.yaml
    ports:
      - "4317:4317"   # OTLP gRPC receiver
      - "4318:4318"   # OTLP HTTP receiver
      - "8889:8889"   # Prometheus metrics exporter
    depends_on:
      - jaeger

  # Distributed Tracing Backend (Jaeger All-In-One)
  jaeger:
    image: jaegertracing/all-in-one:1.56
    container_name: {project_slug}-jaeger
    ports:
      - "16686:16686" # Web UI
      - "14268:14268" # HTTP collector
    environment:
      - COLLECTOR_OTLP_ENABLED=true

  # Metrics TSDB (Prometheus)
  prometheus:
    image: prom/prometheus:v2.51.0
    container_name: {project_slug}-prometheus
    command: ["--config.file=/etc/prometheus/prometheus.yml"]
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  # Dashboards & Observability UI (Grafana)
  grafana:
    image: grafana/grafana:10.4.1
    container_name: {project_slug}-grafana
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana

volumes:
  grafana_data:
"""


def generate_project_telemetry_bundle(
    project_id: Union[UUID, str],
    db: Session
) -> Dict[str, Any]:
    """Generates the full OpenTelemetry and APM Observability bundle for a project."""
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

    slug = sanitize_project_slug(project.name)
    metrics = _generate_metrics_catalog(slug)
    otel_collector_yaml = _generate_otel_collector_config(slug)
    prometheus_yaml = _generate_prometheus_config(slug)
    grafana_dashboard = _generate_grafana_dashboard(project.name, slug)
    middleware_code = _generate_fastapi_telemetry_middleware(slug)
    docker_compose = _generate_telemetry_docker_compose(slug)

    return {
        "project_id": project.id,
        "project_name": project.name,
        "collector_config_yaml": otel_collector_yaml,
        "prometheus_config_yaml": prometheus_yaml,
        "middleware_python_code": middleware_code,
        "docker_compose_yaml": docker_compose,
        "grafana_dashboard_json": grafana_dashboard,
        "metrics_catalog": metrics,
    }
