import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agents.webhook_engine import (
    _compute_hmac_sha256,
    simulate_webhook_dispatch,
    compute_webhook_signature,
    verify_webhook_signature,
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

    # Verify multi-language consumers
    assert "consumer_code_by_lang" in data
    by_lang = data["consumer_code_by_lang"]
    assert "python" in by_lang and "FastAPI" in by_lang["python"]
    assert "nodejs" in by_lang and "crypto.timingSafeEqual" in by_lang["nodejs"]
    assert "go" in by_lang and "hmac.Equal" in by_lang["go"]
    assert "curl" in by_lang and "openssl dgst -sha256 -hmac" in by_lang["curl"]

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


def test_webhook_signature_computation_and_verification():
    secret = "whsec_test_secret_key_abcdef123456"
    payload = {"event": "payment.succeeded", "amount": 4900, "currency": "INR"}

    # 1. Compute signature
    signed = compute_webhook_signature(payload, secret)
    assert signed["signature"].startswith("sha256=")
    assert "t=" in signed["versioned_signature"]
    assert "v1=" in signed["versioned_signature"]

    # 2. Verify valid standard signature
    res_valid = verify_webhook_signature(payload, signed["signature"], secret)
    assert res_valid["valid"] is True
    assert "successfully" in res_valid["reason"].lower()

    # 3. Verify valid versioned signature
    res_v1_valid = verify_webhook_signature(payload, signed["versioned_signature"], secret)
    assert res_v1_valid["valid"] is True

    # 4. Tampered payload fails verification
    tampered = {"event": "payment.succeeded", "amount": 999999, "currency": "INR"}
    res_invalid = verify_webhook_signature(tampered, signed["signature"], secret)
    assert res_invalid["valid"] is False

    # 5. Wrong secret fails verification
    res_wrong_secret = verify_webhook_signature(payload, signed["signature"], "wrong_secret_key")
    assert res_wrong_secret["valid"] is False

    # 6. Replay attack rejection when timestamp is too old
    old_timestamp = signed["timestamp"] - 600  # 10 minutes ago
    res_replay = verify_webhook_signature(
        payload,
        signed["signature"],
        secret,
        timestamp=old_timestamp,
        tolerance_seconds=300,
    )
    assert res_replay["valid"] is False
    assert "replay attack detected" in res_replay["reason"].lower()


def test_webhook_sign_and_verify_api_endpoints():
    # Create project
    p_res = client.post("/projects/", json={
        "name": "Webhook Signature API Test App",
        "brief": "App for testing webhook sign and verify endpoints."
    })
    assert p_res.status_code == 200
    p_id = p_res.json()["id"]

    secret = "whsec_api_endpoint_secret_xyz"
    payload = {"entity": "subscription", "status": "active"}

    # Sign endpoint
    sign_res = client.post(f"/projects/{p_id}/webhooks/sign", json={
        "payload": payload,
        "secret": secret
    })
    assert sign_res.status_code == 200
    sign_data = sign_res.json()
    assert sign_data["signature"].startswith("sha256=")

    # Verify endpoint (success)
    verify_res = client.post(f"/projects/{p_id}/webhooks/verify-signature", json={
        "payload": payload,
        "signature": sign_data["signature"],
        "secret": secret
    })
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["valid"] is True

    # Verify endpoint (tampered failure)
    tampered_res = client.post(f"/projects/{p_id}/webhooks/verify-signature", json={
        "payload": {"entity": "subscription", "status": "canceled"},
        "signature": sign_data["signature"],
        "secret": secret
    })
    assert tampered_res.status_code == 200
    assert tampered_res.json()["valid"] is False

