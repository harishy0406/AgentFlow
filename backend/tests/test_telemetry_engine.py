import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agents.telemetry_engine import (
    _generate_metrics_catalog,
    _generate_otel_collector_config,
    _generate_grafana_dashboard,
    _generate_fastapi_telemetry_middleware,
)

client = TestClient(app)


def test_telemetry_helpers():
    catalog = _generate_metrics_catalog("fintech_app")
    assert len(catalog) >= 5
    metric_names = [m["name"] for m in catalog]
    assert "fintech_app_http_requests_total" in metric_names
    assert "fintech_app_http_request_duration_seconds" in metric_names
    assert "fintech_app_active_in_flight_requests" in metric_names

    otel_yaml = _generate_otel_collector_config("fintech_app")
    assert "receivers:" in otel_yaml
    assert "otlp:" in otel_yaml
    assert "jaeger:4317" in otel_yaml

    dashboard = _generate_grafana_dashboard("Fintech App", "fintech_app")
    assert dashboard["title"] == "Fintech App — APM & Golden Signals"
    assert len(dashboard["panels"]) >= 5
    panel_titles = [p["title"] for p in dashboard["panels"]]
    assert any("Throughput" in t for t in panel_titles)
    assert any("Latency" in t for t in panel_titles)
    assert any("5xx" in t for t in panel_titles)

    middleware = _generate_fastapi_telemetry_middleware("fintech_app")
    assert "class OpenTelemetryTracingMiddleware" in middleware
    assert "traceparent" in middleware
    assert "def setup_telemetry" in middleware


def test_telemetry_api_endpoints():
    # 1. Create and scaffold project
    p_res = client.post("/projects/", json={
        "name": "Enterprise Cloud Hub",
        "brief": "Multi-tenant cloud management platform with high-throughput telemetry."
    })
    assert p_res.status_code == 200
    p_id = p_res.json()["id"]

    client.post(f"/projects/{p_id}/generate")

    # 2. Query telemetry bundle
    tel_res = client.get(f"/projects/{p_id}/telemetry")
    assert tel_res.status_code == 200
    data = tel_res.json()

    assert data["project_id"] == p_id
    assert "receivers:" in data["collector_config_yaml"]
    assert "scrape_configs:" in data["prometheus_config_yaml"]
    assert "class OpenTelemetryTracingMiddleware" in data["middleware_python_code"]
    assert "otel-collector:" in data["docker_compose_yaml"]
    assert "jaeger:" in data["docker_compose_yaml"]
    assert len(data["metrics_catalog"]) >= 5
    assert len(data["grafana_dashboard_json"]["panels"]) >= 5

    # 3. Test Grafana dashboard download endpoint
    dash_res = client.get(f"/projects/{p_id}/telemetry/grafana-dashboard")
    assert dash_res.status_code == 200
    assert "application/json" in dash_res.headers["content-type"]
    assert "attachment" in dash_res.headers.get("content-disposition", "")
    dash_json = dash_res.json()
    assert dash_json["title"] == "Enterprise Cloud Hub — APM & Golden Signals"
