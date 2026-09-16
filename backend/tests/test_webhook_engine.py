import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agents.webhook_engine import (
    _compute_hmac_sha256,
    simulate_webhook_dispatch,
)

client = TestClient(app)


def test_hmac_sha256_computation():
    secret = "whsec_test_secret_123"
    data = b'{"hello":"world"}'
    sig1 = _compute_hmac_sha256(data, secret)
    sig2 = _compute_hmac_sha256(data, secret)
    assert sig1 == sig2
    assert len(sig1) == 64  # 256 bits = 64 hex characters


def test_webhook_simulation_helper():
    res = simulate_webhook_dispatch(
        project_id="00000000-0000-0000-0000-000000000000",
        event_type="order.created",
        target_url="https://api.myclient.com/webhooks",
        secret_key="whsec_custom_secret_key"
    )
    assert res["delivered"] is True
    assert res["status_code"] == 200
    assert res["event_type"] == "order.created"
    assert res["target_url"] == "https://api.myclient.com/webhooks"
    assert res["hmac_signature"].startswith("sha256=")
    assert "X-AgentFlow-Signature-256" in res["headers"]
    assert "X-AgentFlow-Delivery" in res["headers"]
    assert "X-AgentFlow-Timestamp" in res["headers"]
    assert "Idempotency-Key" in res["headers"]
    assert res["retry_policy"]["max_attempts"] == 3


def test_webhook_api_endpoints():
    # 1. Create and scaffold project
    p_res = client.post("/projects/", json={
        "name": "Fintech Payments Gateway",
        "brief": "Secure payments gateway with multi-currency payouts and invoice webhooks."
    })
    assert p_res.status_code == 200
    p_id = p_res.json()["id"]

    client.post(f"/projects/{p_id}/generate")

    # 2. Get event catalog
    events_res = client.get(f"/projects/{p_id}/events")
    assert events_res.status_code == 200
    data = events_res.json()

    assert data["project_id"] == p_id
    assert len(data["events"]) > 0
    first_event = data["events"][0]
    assert "event_type" in first_event
    assert "schema_spec" in first_event
    assert first_event["schema_spec"]["specversion"] == "1.0"
    assert "fintech" in first_event["schema_spec"]["type"].lower()
    assert first_event["schema_spec"]["type"].startswith("com.")

    # Verify code snippets
    assert "class WebhookDispatcher" in data["dispatcher_code"]
    assert "hmac.new" in data["dispatcher_code"]
    assert "def verify_webhook_signature" in data["consumer_code"]
    assert "rabbitmq" in data["broker_docker_compose"]
    assert "redis" in data["broker_docker_compose"]

    # 3. Test Webhook dispatch simulation endpoint
    dispatch_res = client.post(f"/projects/{p_id}/test-webhook", json={
        "event_type": first_event["event_type"],
        "target_url": "https://hooks.stripe.com/test",
        "secret_key": "whsec_super_secret_test_key"
    })
    assert dispatch_res.status_code == 200
    dispatch_data = dispatch_res.json()
    assert dispatch_data["delivered"] is True
    assert dispatch_data["hmac_signature"].startswith("sha256=")
    assert dispatch_data["status_code"] == 200
    assert dispatch_data["duration_ms"] > 0
