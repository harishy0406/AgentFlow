"""
Phase 9: Webhook & Event Broker Architecture Engine

Generates CloudEvents 1.0 compliant domain event definitions,
cryptographic HMAC-SHA256 outbound webhook dispatchers,
idempotent consumer handlers, and event broker infrastructure.
"""

import hmac
import hashlib
import json
import uuid
import re
from datetime import datetime, timezone
from uuid import UUID
from typing import Dict, Any, List, Union, Optional
from sqlalchemy.orm import Session

from ..models import Project, ArtifactNode
from .scaffolder import sanitize_project_slug
from .openapi_generator import _extract_schemas


def _compute_hmac_sha256(payload_bytes: bytes, secret: str) -> str:
    """Computes HMAC-SHA256 signature hex digest."""
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
    return mac.hexdigest()


def _extract_domain_events(project: Project) -> List[Dict[str, Any]]:
    """Extracts or infers domain events from project artifacts and database schemas."""
    db_node = next((n for n in project.artifact_nodes if n.artifact_type == "DB_SCHEMA"), None)
    db_text = "\n\n".join(s.content for s in db_node.sections) if db_node and db_node.sections else ""
    schemas = _extract_schemas(db_text)
    events = []

    target_entities = list(schemas.keys())
    if not target_entities:
        # Fallback default entities based on project name or standard SaaS
        target_entities = ["User", "Project", "Notification"]


    for entity in target_entities[:6]:  # Keep clean top entities
        ent_lower = entity.lower()
        properties = schemas.get(entity, {"id": "uuid", "created_at": "datetime"})
        sample_data = {}
        for prop, ptype in properties.items():
            if "uuid" in str(ptype).lower() or "id" in prop.lower():
                sample_data[prop] = str(uuid.uuid4())
            elif "int" in str(ptype).lower():
                sample_data[prop] = 1001
            elif "date" in str(ptype).lower() or "time" in prop.lower():
                sample_data[prop] = datetime.now(timezone.utc).isoformat()
            elif "bool" in str(ptype).lower():
                sample_data[prop] = True
            else:
                sample_data[prop] = f"sample_{prop}"

        for action in ["created", "updated", "deleted"]:
            event_type = f"{ent_lower}.{action}"
            events.append({
                "event_type": event_type,
                "entity": entity,
                "action": action,
                "description": f"Triggered immediately when a {entity} resource is {action}.",
                "schema_spec": {
                    "specversion": "1.0",
                    "type": f"com.{sanitize_project_slug(project.name)}.{event_type}",
                    "source": f"/{ent_lower}s",
                    "id": str(uuid.uuid4()),
                    "time": datetime.now(timezone.utc).isoformat(),
                    "datacontenttype": "application/json",
                    "data": sample_data
                }
            })

    return events


def _generate_webhook_dispatcher_code(project_slug: str, events: List[Dict[str, Any]]) -> str:
    """Generates production-grade outbound webhook dispatcher with HMAC and retry policies."""
    return f'''"""
{project_slug.upper()} Outbound Webhook Dispatcher
Engineered with HMAC-SHA256 signature generation, exponential backoff retries,
and CloudEvents 1.0 compliance.
"""

import hmac
import hashlib
import json
import time
import uuid
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger("webhooks.dispatcher")


class WebhookDispatcher:
    def __init__(
        self,
        secret_key: str,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
        timeout: float = 10.0
    ):
        self.secret_key = secret_key
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.timeout = timeout

    def sign_payload(self, payload_bytes: bytes) -> str:
        """Generates hex-encoded HMAC-SHA256 signature for webhook payload."""
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        return f"sha256={{signature}}"

    async def dispatch(
        self,
        target_url: str,
        event_type: str,
        data: Dict[str, Any],
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Dispatches an event payload with exponential retry and delivery verification."""
        delivery_id = str(uuid.uuid4())
        idem_key = idempotency_key or str(uuid.uuid4())
        timestamp = str(int(time.time()))

        cloud_event = {{
            "specversion": "1.0",
            "id": delivery_id,
            "type": f"com.{project_slug}.{{event_type}}",
            "source": f"https://api.{project_slug}.com",
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "datacontenttype": "application/json",
            "data": data,
        }}

        body_bytes = json.dumps(cloud_event, separators=(",", ":")).encode("utf-8")
        signature = self.sign_payload(body_bytes)

        headers = {{
            "Content-Type": "application/json",
            "User-Agent": "{project_slug}-Webhooks/1.0",
            "X-AgentFlow-Delivery": delivery_id,
            "X-AgentFlow-Event": event_type,
            "X-AgentFlow-Timestamp": timestamp,
            "X-AgentFlow-Signature-256": signature,
            "Idempotency-Key": idem_key,
        }}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            attempt = 0
            while attempt < self.max_retries:
                attempt += 1
                try:
                    start_time = time.perf_counter()
                    resp = await client.post(target_url, content=body_bytes, headers=headers)
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    if resp.is_success:
                        logger.info(
                            "Webhook delivered successfully: %s to %s (status %d, %0.2fms)",
                            delivery_id, target_url, resp.status_code, duration_ms
                        )
                        return {{
                            "delivery_id": delivery_id,
                            "delivered": True,
                            "status_code": resp.status_code,
                            "attempts": attempt,
                            "duration_ms": duration_ms
                        }}

                    logger.warning(
                        "Webhook non-2xx response: attempt %d/%d (status %d)",
                        attempt, self.max_retries, resp.status_code
                    )
                except httpx.RequestError as exc:
                    logger.error("Webhook network error on attempt %d/%d: %s", attempt, self.max_retries, exc)

                if attempt < self.max_retries:
                    sleep_duration = self.backoff_factor ** attempt
                    await httpx.sleep(sleep_duration)

        return {{
            "delivery_id": delivery_id,
            "delivered": False,
            "status_code": 0,
            "attempts": self.max_retries,
            "error": "Max retries exceeded"
        }}
'''


def _generate_webhook_consumer_code(project_slug: str, events: List[Dict[str, Any]]) -> str:
    """Generates idempotent consumer handler with timing-safe signature verification."""
    return f'''"""
{project_slug.upper()} Inbound Webhook Consumer Handler
Implements timing-safe HMAC validation, replay-attack prevention, and idempotency tracking.
"""

import hmac
import hashlib
import time
from fastapi import FastAPI, Request, HTTPException, Header, status

app = FastAPI(title="{project_slug.capitalize()} Inbound Webhook Listener")
WEBHOOK_SECRET = "whsec_agentflow_default_secret_key"
PROCESSED_DELIVERY_IDS = set()  # In production, back with Redis with 24h TTL


def verify_webhook_signature(payload_bytes: bytes, signature_header: str, timestamp_header: str) -> bool:
    """Verifies HMAC-SHA256 signature and prevents replay attacks outside 300s window."""
    try:
        ts = int(timestamp_header)
        current_ts = int(time.time())
        if abs(current_ts - ts) > 300:  # 5 minutes replay window
            return False
    except (ValueError, TypeError):
        return False

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected_sig = signature_header.split("sha256=")[-1]
    computed_sig = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    # Timing-safe comparison to prevent side-channel attacks
    return hmac.compare_digest(expected_sig, computed_sig)


@app.post("/webhooks/listener", status_code=status.HTTP_200_OK)
async def receive_webhook(
    request: Request,
    x_agentflow_delivery: str = Header(None),
    x_agentflow_event: str = Header(None),
    x_agentflow_timestamp: str = Header(None),
    x_agentflow_signature_256: str = Header(None),
):
    body = await request.body()

    # 1. Signature & Timestamp Validation
    if not verify_webhook_signature(body, x_agentflow_signature_256, x_agentflow_timestamp):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC signature or expired timestamp"
        )

    # 2. Idempotency Check
    if x_agentflow_delivery in PROCESSED_DELIVERY_IDS:
        return {{"status": "duplicate_ignored", "delivery_id": x_agentflow_delivery}}

    PROCESSED_DELIVERY_IDS.add(x_agentflow_delivery)

    # 3. Process Event Payload
    event_data = await request.json()
    # Route event based on x_agentflow_event (e.g. order.created)
    return {{"status": "processed", "event": x_agentflow_event, "delivery_id": x_agentflow_delivery}}
'''


def _generate_webhook_consumer_node(project_slug: str, events: List[Dict[str, Any]]) -> str:
    """Generates Node.js Express webhook consumer with timingSafeEqual and replay protection."""
    return f'''/**
 * {project_slug.upper()} Inbound Webhook Consumer Handler (Node.js / Express)
 * Implements crypto.timingSafeEqual HMAC-SHA256 validation, replay-attack prevention,
 * and memory-safe idempotency tracking.
 */

const express = require('express');
const crypto = require('crypto');

const app = express();
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || "whsec_agentflow_default_secret_key";
const PROCESSED_DELIVERIES = new Set(); // In production, back with Redis (SET key 1 EX 86400)

// Capture raw body buffer for authentic cryptographic HMAC verification
app.use(express.json({{
  verify: (req, res, buf) => {{
    req.rawBody = buf;
  }}
}}));

function verifyWebhookSignature(rawBody, signatureHeader, timestampHeader) {{
  if (!rawBody || !signatureHeader || !timestampHeader) return false;

  // 1. Replay attack window check (5 minutes = 300s)
  const timestamp = parseInt(timestampHeader, 10);
  const now = Math.floor(Date.now() / 1000);
  if (isNaN(timestamp) || Math.abs(now - timestamp) > 300) {{
    return false;
  }}

  if (!signatureHeader.startsWith('sha256=')) return false;
  const providedSignature = signatureHeader.slice(7);

  // 2. Compute expected HMAC-SHA256
  const computedSignature = crypto
    .createHmac('sha256', WEBHOOK_SECRET)
    .update(rawBody)
    .digest('hex');

  // 3. Timing-safe comparison to prevent side-channel timing attacks
  const expectedBuf = Buffer.from(providedSignature, 'hex');
  const computedBuf = Buffer.from(computedSignature, 'hex');
  if (expectedBuf.length !== computedBuf.length) return false;

  return crypto.timingSafeEqual(expectedBuf, computedBuf);
}}

app.post('/webhooks/listener', (req, res) => {{
  const deliveryId = req.header('X-AgentFlow-Delivery');
  const eventType = req.header('X-AgentFlow-Event');
  const timestamp = req.header('X-AgentFlow-Timestamp');
  const signature = req.header('X-AgentFlow-Signature-256');

  // Verify HMAC signature
  if (!verifyWebhookSignature(req.rawBody, signature, timestamp)) {{
    return res.status(401).json({{
      error: 'Invalid signature or expired timestamp',
      status: 401
    }});
  }}

  // Idempotency de-duplication
  if (deliveryId && PROCESSED_DELIVERIES.has(deliveryId)) {{
    return res.status(200).json({{
      status: 'duplicate_ignored',
      delivery_id: deliveryId
    }});
  }}
  if (deliveryId) PROCESSED_DELIVERIES.add(deliveryId);

  // Dispatch domain event handling
  console.log(`[Webhook Received] Event: ${{eventType}}, Delivery: ${{deliveryId}}`);
  return res.status(200).json({{
    status: 'processed',
    event: eventType,
    delivery_id: deliveryId
  }});
}});

const PORT = process.env.PORT || 8000;
app.listen(PORT, () => {{
  console.log(`{project_slug.capitalize()} webhook listener running on port ${{PORT}}`);
}});
'''


def _generate_webhook_consumer_go(project_slug: str, events: List[Dict[str, Any]]) -> str:
    """Generates Go net/http webhook consumer with hmac.Equal and replay prevention."""
    return f'''package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	WebhookSecret = "whsec_agentflow_default_secret_key"
	ReplayWindow  = 300 // seconds
)

var (
	processedDeliveries = make(map[string]bool)
	mu                  sync.Mutex
)

func verifyWebhookSignature(payload []byte, sigHeader, tsHeader string) bool {{
	ts, err := strconv.ParseInt(tsHeader, 10, 64)
	if err != nil {{
		return false
	}}
	if math.Abs(float64(time.Now().Unix()-ts)) > ReplayWindow {{
		return false // Expired timestamp / replay attack
	}}

	if !strings.HasPrefix(sigHeader, "sha256=") {{
		return false
	}}
	providedSig := strings.TrimPrefix(sigHeader, "sha256=")
	providedBytes, err := hex.DecodeString(providedSig)
	if err != nil {{
		return false
	}}

	mac := hmac.New(sha256.New, []byte(WebhookSecret))
	mac.Write(payload)
	computedBytes := mac.Sum(nil)

	// Constant-time comparison
	return hmac.Equal(providedBytes, computedBytes)
}}

func webhookHandler(w http.ResponseWriter, r *http.Request) {{
	if r.Method != http.MethodPost {{
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}}

	deliveryID := r.Header.Get("X-AgentFlow-Delivery")
	eventType := r.Header.Get("X-AgentFlow-Event")
	timestamp := r.Header.Get("X-AgentFlow-Timestamp")
	signature := r.Header.Get("X-AgentFlow-Signature-256")

	body, err := io.ReadAll(r.Body)
	if err != nil {{
		http.Error(w, "Cannot read body", http.StatusBadRequest)
		return
	}}

	if !verifyWebhookSignature(body, signature, timestamp) {{
		http.Error(w, "Invalid HMAC signature or expired timestamp", http.StatusUnauthorized)
		return
	}}

	mu.Lock()
	if processedDeliveries[deliveryID] {{
		mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{{"status": "duplicate_ignored", "delivery_id": deliveryID}})
		return
	}}
	processedDeliveries[deliveryID] = true
	mu.Unlock()

	log.Printf("[Webhook OK] %s event=%s id=%s\\n", "{project_slug}", eventType, deliveryID)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{{"status": "processed", "event": eventType, "delivery_id": deliveryID}})
}}

func main() {{
	http.HandleFunc("/webhooks/listener", webhookHandler)
	fmt.Println("{project_slug.capitalize()} Go Webhook Receiver listening on :8000")
	log.Fatal(http.ListenAndServe(":8000", nil))
}}
'''


def _generate_webhook_test_curl(project_slug: str, events: List[Dict[str, Any]]) -> str:
    """Generates ready-to-execute cURL testing snippet with HMAC-SHA256 signature generation."""
    sample_event = events[0]["event_type"] if events else "order.created"
    return f'''#!/usr/bin/env bash
# ==============================================================================
# {project_slug.upper()} Cryptographic Webhook Test Script (HMAC-SHA256)
# Computes UNIX epoch timestamp & authentic hex digest matching AgentFlow spec
# ==============================================================================

WEBHOOK_URL="http://localhost:8000/webhooks/listener"
SECRET="whsec_agentflow_default_secret_key"
EVENT_TYPE="{sample_event}"
DELIVERY_ID=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "del_test_1001")
TIMESTAMP=$(date +%s)

PAYLOAD=$(cat <<EOF
{{
  "specversion": "1.0",
  "id": "$DELIVERY_ID",
  "type": "com.{project_slug}.$EVENT_TYPE",
  "source": "/api/v1/events",
  "time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "datacontenttype": "application/json",
  "data": {{
    "test": true,
    "event": "$EVENT_TYPE",
    "dispatched_by": "AgentFlow CLI Tester"
  }}
}}
EOF
)

# Compute HMAC-SHA256 hex digest
SIGNATURE_HEX=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')
SIGNATURE_HEADER="sha256=$SIGNATURE_HEX"

echo "Dispatched delivery ID: $DELIVERY_ID"
echo "Timestamp: $TIMESTAMP"
echo "Computed Signature: $SIGNATURE_HEADER"

curl -i -X POST "$WEBHOOK_URL" \\
  -H "Content-Type: application/json" \\
  -H "User-Agent: AgentFlow-WebhookTester/1.0" \\
  -H "X-AgentFlow-Delivery: $DELIVERY_ID" \\
  -H "X-AgentFlow-Event: $EVENT_TYPE" \\
  -H "X-AgentFlow-Timestamp: $TIMESTAMP" \\
  -H "X-AgentFlow-Signature-256: $SIGNATURE_HEADER" \\
  -H "Idempotency-Key: $(uuidgen 2>/dev/null || echo "idem_1001")" \\
  -d "$PAYLOAD"
'''


def _generate_broker_docker_compose(project_slug: str) -> str:
    """Generates ready-to-run Docker Compose for Redis & RabbitMQ event message brokers."""
    return f"""version: '3.8'

services:
  # RabbitMQ AMQP Message Broker with Management Dashboard
  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    container_name: {project_slug}-rabbitmq
    ports:
      - "5672:5672"    # AMQP protocol
      - "15672:15672"  # Management Web UI (guest:guest)
    environment:
      RABBITMQ_DEFAULT_USER: {project_slug}_admin
      RABBITMQ_DEFAULT_PASS: secure_broker_password
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "check_port_connectivity"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis In-Memory Pub/Sub & Webhook Idempotency Store
  redis:
    image: redis:7-alpine
    container_name: {project_slug}-redis-events
    command: ["redis-server", "--appendonly", "yes", "--requirepass", "redis_broker_secret"]
    ports:
      - "6379:6379"
    volumes:
      - redis_event_data:/data

volumes:
  rabbitmq_data:
  redis_event_data:
"""


def generate_project_event_catalog(
    project_id: Union[UUID, str],
    db: Session
) -> Dict[str, Any]:
    """Generates the comprehensive Event Catalog, Dispatcher code, and Broker compose."""
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
    events = _extract_domain_events(project)
    dispatcher_code = _generate_webhook_dispatcher_code(slug, events)
    consumer_code_python = _generate_webhook_consumer_code(slug, events)
    consumer_code_node = _generate_webhook_consumer_node(slug, events)
    consumer_code_go = _generate_webhook_consumer_go(slug, events)
    consumer_code_curl = _generate_webhook_test_curl(slug, events)
    broker_compose = _generate_broker_docker_compose(slug)

    consumer_code_by_lang = {
        "python": consumer_code_python,
        "nodejs": consumer_code_node,
        "go": consumer_code_go,
        "curl": consumer_code_curl,
    }

    return {
        "project_id": project.id,
        "project_name": project.name,
        "events": events,
        "dispatcher_code": dispatcher_code,
        "consumer_code": consumer_code_python,
        "consumer_code_by_lang": consumer_code_by_lang,
        "broker_docker_compose": broker_compose,
    }


def simulate_webhook_dispatch(
    project_id: Union[UUID, str],
    event_type: str,
    target_url: str = "https://api.example.com/webhooks",
    secret_key: Optional[str] = "whsec_agentflow_default_secret_key",
    custom_payload: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Simulates real-time cryptographic webhook dispatch with authentic HMAC-SHA256 signature,
    headers, and delivery lifecycle metadata.
    """
    secret = secret_key or "whsec_agentflow_default_secret_key"
    delivery_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    ts_str = str(int(now.timestamp()))

    payload = custom_payload or {
        "specversion": "1.0",
        "id": delivery_id,
        "type": f"com.agentflow.{event_type}",
        "source": "/api/v1/events",
        "time": now.isoformat(),
        "datacontenttype": "application/json",
        "data": {
            "id": str(uuid.uuid4()),
            "status": "completed",
            "message": f"Event {event_type} dispatched successfully."
        }
    }

    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_bytes = payload_json.encode("utf-8")
    hex_digest = _compute_hmac_sha256(payload_bytes, secret)
    signature = f"sha256={hex_digest}"

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AgentFlow-WebhookDelivery/1.0",
        "X-AgentFlow-Delivery": delivery_id,
        "X-AgentFlow-Event": event_type,
        "X-AgentFlow-Timestamp": ts_str,
        "X-AgentFlow-Signature-256": signature,
        "Idempotency-Key": str(uuid.uuid4()),
    }

    # Simulate fast realistic HTTP delivery execution (18ms - 42ms)
    duration_ms = 24.8

    return {
        "delivery_id": delivery_id,
        "event_type": event_type,
        "target_url": target_url,
        "timestamp": now.isoformat(),
        "headers": headers,
        "payload": payload,
        "hmac_signature": signature,
        "status_code": 200,
        "duration_ms": duration_ms,
        "delivered": True,
        "retry_policy": {
            "max_attempts": 3,
            "backoff_multiplier": 1.5,
            "dead_letter_queue": "arn:agentflow:dlq:webhooks-failed"
        }
    }
