import re
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.models import Project, ArtifactNode, ArtifactSection
from app.schemas import ArchitectureDecisionRecord, AdrCatalogOut


def _extract_project_context(project_id: str, db: Session) -> Dict[str, str]:
    target_id = UUID(project_id) if isinstance(project_id, str) else project_id
    project = db.query(Project).filter(Project.id == target_id).first()
    if not project:
        raise ValueError(f"Project with ID '{project_id}' not found")

    nodes = db.query(ArtifactNode).filter(ArtifactNode.project_id == target_id).all()
    sections_by_type: Dict[str, str] = {}

    for node in nodes:
        sections = db.query(ArtifactSection).filter(ArtifactSection.artifact_node_id == node.id).all()
        combined = "\n\n".join([s.content for s in sections if s.content])
        sections_by_type[node.artifact_type] = combined

    return {
        "name": project.name,
        "brief": project.brief or "Autonomous scalable system architecture.",
        "prd": sections_by_type.get("PRD", ""),
        "sdd": sections_by_type.get("SDD", ""),
        "db_schema": sections_by_type.get("DB_SCHEMA", ""),
        "api_spec": sections_by_type.get("API_SPEC", ""),
        "tasks": sections_by_type.get("TASKS", ""),
    }


def generate_project_adrs(project_id: str, db: Session) -> AdrCatalogOut:
    target_id = UUID(project_id) if isinstance(project_id, str) else project_id
    project = db.query(Project).filter(Project.id == target_id).first()
    if not project:
        raise ValueError(f"Project with ID '{project_id}' not found")

    ctx = _extract_project_context(str(project.id), db)
    app_name = ctx["name"]
    brief = ctx["brief"]
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    adrs: List[ArchitectureDecisionRecord] = []

    # -----------------------------------------------------------------------
    # ADR-0001: Primary Relational Persistence Engine
    # -----------------------------------------------------------------------
    adr1_md = f"""# ADR-0001: Selection of Primary Relational Persistence Engine (PostgreSQL)

- **Status**: ACCEPTED
- **Date**: {today_str}
- **Deciders**: Lead System Architect, Database Architect, DevOps Engineer
- **Technical Story**: Establish the primary persistence engine for {app_name}.

## Context and Problem Statement
{app_name} requires a durable, ACID-compliant persistence tier capable of enforcing relational integrity, structured transactions, and schema evolution. The system brief states:
> "{brief}"

We need a database engine that balances strict transactional correctness, high concurrent throughput, and rich query capabilities (JSONB, full-text search, window functions).

## Decision Drivers
- Strict ACID compliance for core business state and transactional consistency.
- Robust ecosystem support for migration tooling (Alembic) and connection pooling.
- Support for semi-structured data (JSONB) alongside relational tables.
- Availability of managed cloud offerings across AWS (RDS/Aurora), GCP (Cloud SQL), and Azure.

## Considered Options
1. **PostgreSQL 15+ with Alembic / SQLAlchemy ORM**
2. **MongoDB Document Database**
3. **Apache Cassandra / DynamoDB Distributed NoSQL**

## Decision Outcome
Chosen option: **PostgreSQL 15+**, because {app_name}'s domain demands relational integrity between entities, foreign key constraints, and declarative schema migrations.

### Positive Consequences
- Guarantees strict transactional consistency and eliminates race conditions.
- Rich ecosystem of analytical extensions, index types (B-tree, GIN), and JSONB operators.
- Seamless multi-cloud portability via standard managed database services.

### Negative Consequences
- Vertical write scaling requires read replicas and connection pool management (e.g. PgBouncer).
- Schema alterations require planned zero-downtime migration scripts.
"""
    adrs.append(ArchitectureDecisionRecord(
        id="ADR-0001",
        title="Selection of Primary Relational Persistence Engine (PostgreSQL)",
        status="ACCEPTED",
        date=today_str,
        deciders=["Lead System Architect", "Database Architect", "DevOps Engineer"],
        context=f"{app_name} requires durable, ACID-compliant persistence for relational integrity and transactional consistency based on: {brief[:160]}...",
        decision_drivers=["Strict ACID compliance", "Relational foreign keys & schema migrations", "JSONB support", "Multi-cloud availability"],
        considered_options=["PostgreSQL 15+ with Alembic", "MongoDB Document Database", "DynamoDB NoSQL"],
        decision_outcome="Selected PostgreSQL 15+ for strict consistency, transactional integrity, and mature migration tooling.",
        consequences_positive=["Guaranteed transactional integrity", "Rich indexing and querying", "Multi-cloud support"],
        consequences_negative=["Write scaling requires read-replica topology", "Requires migration discipline"],
        markdown_content=adr1_md
    ))

    # -----------------------------------------------------------------------
    # ADR-0002: Modular Multi-Agent Directed Acyclic Graph (DAG) Pipeline
    # -----------------------------------------------------------------------
    adr2_md = f"""# ADR-0002: Modular Multi-Agent Directed Acyclic Graph (DAG) Execution Model

- **Status**: ACCEPTED
- **Date**: {today_str}
- **Deciders**: AI Platform Architect, Product Owner Agent, Software Engineering Lead
- **Technical Story**: Design the multi-agent orchestration pattern for automated artifact generation.

## Context and Problem Statement
Traditional monolithic LLM prompts attempt to generate requirements, system designs, and code in a single generation step. This causes compounding hallucinations, lack of verification gates, and catastrophic token costs whenever an upstream requirement shifts.

## Decision Drivers
- Isolation of concerns: each engineering domain (PRD, Architecture, DB, API, Code) handled by specialized agents.
- Incremental recomputation: recomputing only downstream nodes when an artifact changes.
- Artifact-specific LLM routing: mapping each task to the most competent model.
- Auditability: every artifact must have typed dependencies and cryptographic content hashes.

## Considered Options
1. **Typed Directed Acyclic Graph (DAG) with Invalidation Engine**
2. **Single Monolithic Prompt Chain**
3. **Free-form Autonomous Loop without Deterministic Dependency Tracking**

## Decision Outcome
Chosen option: **Typed Directed Acyclic Graph (DAG)**. Each artifact is an immutable node in a dependency graph. When an artifact is edited, only its direct and transitive downstream dependents are invalidated.

### Positive Consequences
- 60-80% reduction in token consumption on requirement iterations.
- Full provenance and version history per artifact section.
- Decoupled testing and verification per agent role.

### Negative Consequences
- Increased architectural complexity in state management and topological sorting.
"""
    adrs.append(ArchitectureDecisionRecord(
        id="ADR-0002",
        title="Modular Multi-Agent Directed Acyclic Graph (DAG) Execution Model",
        status="ACCEPTED",
        date=today_str,
        deciders=["AI Platform Architect", "Product Owner Agent", "Software Engineering Lead"],
        context="Monolithic LLM prompt chains compound hallucinations and waste tokens on minor requirement changes.",
        decision_drivers=["Separation of engineering concerns", "Incremental dependency recomputation", "Cost optimization via model routing", "Cryptographic auditability"],
        considered_options=["Typed DAG with Invalidation Engine", "Monolithic Prompt Chain", "Free-form Autonomous Loop"],
        decision_outcome="Adopted Typed DAG with invalidation engine to achieve deterministic incremental artifact regeneration.",
        consequences_positive=["Drastically reduced iteration cost", "Verifiable state per node", "Domain-specialized agent prompts"],
        consequences_negative=["Higher orchestration complexity", "Requires topological graph engine"],
        markdown_content=adr2_md
    ))

    # -----------------------------------------------------------------------
    # ADR-0003: RESTful API Protocol with Strict OpenAPI 3.0.3 Contract-First
    # -----------------------------------------------------------------------
    adr3_md = f"""# ADR-0003: RESTful API Protocol with Strict OpenAPI 3.0.3 Contract-First Design

- **Status**: ACCEPTED
- **Date**: {today_str}
- **Deciders**: API Designer Agent, Frontend Architect, Security Reviewer
- **Technical Story**: Standardize the external and inter-service communication protocol.

## Context and Problem Statement
{app_name} exposes programmatic capabilities to client applications, third-party integrations, and frontend dashboards. We require an API specification standard that enables automated SDK generation, contract testing, and mock execution.

## Decision Drivers
- Broad client compatibility across TypeScript, Python, Go, and cURL.
- Standardized OpenAPI 3.0.3 tooling for Swagger UI, Postman, and automated mock engines.
- Type-safe schema validation at the HTTP boundary via Pydantic.

## Considered Options
1. **RESTful HTTP/JSON with OpenAPI 3.0.3 Specification**
2. **gRPC with Protocol Buffers**
3. **Pure GraphQL API**

## Decision Outcome
Chosen option: **RESTful HTTP/JSON with OpenAPI 3.0.3**. This allows seamless client consumption, native browser HTTP caching, standard status codes (200, 201, 400, 404, 500), and automated client SDK synthesis.

### Positive Consequences
- Ubiquitous browser and developer tooling compatibility.
- Instant Postman Collection and dynamic mock sandbox generation.
- Clear HTTP semantic caching and idempotent verbs (`GET`, `PUT`, `DELETE`).

### Negative Consequences
- Multiple network hops required for deeply nested resources compared to single GraphQL queries.
"""
    adrs.append(ArchitectureDecisionRecord(
        id="ADR-0003",
        title="RESTful API Protocol with Strict OpenAPI 3.0.3 Contract-First Design",
        status="ACCEPTED",
        date=today_str,
        deciders=["API Designer Agent", "Frontend Architect", "Security Reviewer"],
        context="Inter-service and client communication requires standardized contract definition for automated SDK and test generation.",
        decision_drivers=["Broad client compatibility", "OpenAPI ecosystem maturity", "Pydantic type-safety at boundary"],
        considered_options=["REST with OpenAPI 3.0.3", "gRPC / Protobuf", "Pure GraphQL"],
        decision_outcome="Selected REST with OpenAPI 3.0.3 for universal client interoperability and rich ecosystem tooling.",
        consequences_positive=["Immediate Postman and SDK generation", "Standard HTTP semantics and status codes"],
        consequences_negative=["Potential over-fetching for specialized mobile views"],
        markdown_content=adr3_md
    ))

    # -----------------------------------------------------------------------
    # ADR-0004: Event-Driven Webhook Dispatch & Asynchronous Message Broker
    # -----------------------------------------------------------------------
    adr4_md = f"""# ADR-0004: Event-Driven Webhook Dispatch & Asynchronous Message Broker

- **Status**: ACCEPTED
- **Date**: {today_str}
- **Deciders**: Backend Lead, Integration Specialist, Security Architect
- **Technical Story**: Decouple synchronous HTTP request handling from background job execution and external notifications.

## Context and Problem Statement
Long-running agent workflows, third-party webhook dispatches, and heavy PDF report compilations must not block the synchronous FastAPI request thread. Furthermore, downstream consumers need reliable asynchronous event notifications with HMAC-SHA256 signatures.

## Decision Drivers
- Sub-50ms API response latency for client requests.
- Guaranteed at-least-once message delivery with dead-letter queueing (DLQ).
- Cryptographic verification of outgoing webhooks for external integrations.

## Considered Options
1. **RabbitMQ / Redis Queue with Celery / BackgroundTasks Worker Pool**
2. **Synchronous In-Process Execution**
3. **Apache Kafka Streaming Cluster**

## Decision Outcome
Chosen option: **RabbitMQ / Redis Worker Pool** with HMAC-SHA256 signed webhooks. Lightweight, highly reliable, and supported natively in Docker Compose and Kubernetes.

### Positive Consequences
- Fast, non-blocking synchronous endpoints.
- Resilient retry policies with exponential backoff for failed webhook endpoints.
- Secure payload delivery with replay prevention.

### Negative Consequences
- Requires additional message broker infrastructure (Redis/RabbitMQ container).
"""
    adrs.append(ArchitectureDecisionRecord(
        id="ADR-0004",
        title="Event-Driven Webhook Dispatch & Asynchronous Message Broker",
        status="ACCEPTED",
        date=today_str,
        deciders=["Backend Lead", "Integration Specialist", "Security Architect"],
        context="Heavy generation tasks, report compilation, and outbound webhooks must not block client HTTP request cycles.",
        decision_drivers=["Low latency HTTP responses", "At-least-once delivery with DLQ", "HMAC-SHA256 security signatures"],
        considered_options=["RabbitMQ / Redis Worker Pool", "Synchronous In-Process Execution", "Apache Kafka"],
        decision_outcome="Selected RabbitMQ / Redis message broker with signed webhooks for robust asynchronous processing.",
        consequences_positive=["Decoupled async workflows", "Exponential backoff retries", "Standard HMAC security verification"],
        consequences_negative=["Operational overhead of broker service"],
        markdown_content=adr4_md
    ))

    # -----------------------------------------------------------------------
    # ADR-0005: Declarative Multi-Cloud Infrastructure as Code (Terraform & K8s)
    # -----------------------------------------------------------------------
    adr5_md = f"""# ADR-0005: Declarative Multi-Cloud Infrastructure as Code (Terraform & Kubernetes)

- **Status**: ACCEPTED
- **Date**: {today_str}
- **Deciders**: DevOps Lead, Security Architect, Cloud Operations Team
- **Technical Story**: Define standard provisioning and container orchestration strategy for {app_name}.

## Context and Problem Statement
Production deployment must be reproducible, version-controlled, and agnostic to any single cloud provider lock-in. Environments (Development, Staging, Production) must be identical in topology.

## Decision Drivers
- Cloud-agnostic provisioning (AWS, GCP, Azure, or bare-metal).
- GitOps-compatible immutable infrastructure definition.
- Declarative container scaling, health checks, and rolling zero-downtime updates.

## Considered Options
1. **Terraform Modules paired with Cloud-Native Kubernetes Manifests**
2. **Cloud-Specific Templates (AWS CloudFormation / GCP Cloud Deployment Manager)**
3. **Manual Cloud Console Provisioning**

## Decision Outcome
Chosen option: **Terraform + Kubernetes**. Terraform manages cloud network, managed DB, and VPC infrastructure; Kubernetes handles container scheduling, ingress, secrets, and autoscaling.

### Positive Consequences
- 100% reproducible environments across cloud providers.
- Automated CI/CD integration with preview and rollback mechanisms.
- Cloud cost portability without rewrite.

### Negative Consequences
- Steeper learning curve for Kubernetes cluster administration.
"""
    adrs.append(ArchitectureDecisionRecord(
        id="ADR-0005",
        title="Declarative Multi-Cloud Infrastructure as Code (Terraform & Kubernetes)",
        status="ACCEPTED",
        date=today_str,
        deciders=["DevOps Lead", "Security Architect", "Cloud Operations Team"],
        context="Deployment requires reproducible, cloud-agnostic, and version-controlled infrastructure provisioning.",
        decision_drivers=["Cloud-agnostic portability", "GitOps compatibility", "Automated scaling and healthchecks"],
        considered_options=["Terraform + Kubernetes", "CloudFormation / Cloud Deployment Manager", "Manual Console Configuration"],
        decision_outcome="Adopted Terraform for infrastructure and Kubernetes for container orchestration.",
        consequences_positive=["Complete environment reproducibility", "Eliminates vendor lock-in", "Zero-downtime rolling updates"],
        consequences_negative=["Requires container runtime and cluster management expertise"],
        markdown_content=adr5_md
    ))

    # Generate master index markdown
    index_md = f"""# Architecture Decision Log — {app_name}

> Generated on {today_str} by AgentFlow Architecture Decision Engine.

| ADR ID | Title | Status | Date |
|---|---|---|---|
"""
    for a in adrs:
        index_md += f"| **{a.id}** | {a.title} | `{a.status}` | {a.date} |\n"

    index_md += "\n---\n\n## Summary of Architecture Foundations\n\n"
    index_md += f"1. **Persistence**: PostgreSQL 15+ for strict ACID compliance and relational integrity.\n"
    index_md += f"2. **Execution Engine**: Typed DAG with diff-aware invalidation and targeted recomputation.\n"
    index_md += f"3. **API Protocol**: RESTful OpenAPI 3.0.3 specification with automated SDK synthesis.\n"
    index_md += f"4. **Async & Integration**: RabbitMQ/Redis event queue with HMAC-SHA256 webhook dispatch.\n"
    index_md += f"5. **Provisioning**: Multi-Cloud Terraform modules and Kubernetes container manifests.\n"

    return AdrCatalogOut(
        project_id=project.id,
        project_name=project.name,
        total_adrs=len(adrs),
        adrs=adrs,
        index_markdown=index_md
    )
