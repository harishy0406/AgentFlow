# AgentFlow Implementation Plan

This document outlines the end-to-end, phase-wise implementation plan for the AgentFlow platform based on the Product Requirements Document (PRD), Software Design Document (SDD), and Architecture Document. 

## Goal Description

AgentFlow is an adaptive multi-agent workflow orchestration platform that automates the generation, synchronization, and evolution of software engineering artifacts. The goal is to build a system that supports **dependency-aware selective regeneration**, **artifact-specific quality-signal routing**, and **continuous cross-artifact consistency auditing**.

## User Review Required

> [!IMPORTANT]
> Please review the phasing and scope of this implementation plan. Specifically, confirm if the chosen LLM providers (e.g., Anthropic, OpenAI) for Phase 3 and the deployment strategy for the evaluation harness in Phase 6 align with your current resources and constraints.

## Open Questions

> [!WARNING]
> 1. Do you have preferred tools for the evaluation harness dataset (e.g., specific 15-20 project briefs already prepared)?
> 2. Are there any specific requirements for the initial single-model to be used in Phase 1 before the multi-provider routing is implemented?
> 3. Should the Pinecone vector store setup be prioritized earlier if semantic context retrieval is deemed critical for the initial generation pipeline?

---

## Proposed Phases & Changes

### Phase 1: Core Foundation & Single-Model Pipeline

**Objective:** Establish the fundamental data models, the static dependency graph, and a basic sequential multi-agent generation pipeline using a single LLM provider.

- **Setup & Infrastructure:**
  - Initialize the FastAPI backend project.
  - Set up PostgreSQL and define the core SQLAlchemy models (`projects`, `artifact_nodes`, `artifact_sections`, `section_traces`).
  - Configure Redis for basic caching and state management.
- **Agent Layer (LangGraph):**
  - Implement the LangGraph orchestrator.
  - Create the 6 base agent nodes (Business Analyst, System Designer, Database Architect, API Designer, QA Engineer, Project Planner).
  - Define the Pydantic schemas for their input/output contracts.
- **Generation Logic & HITL:**
  - Implement a Human-in-the-Loop (HITL) interactive step: an agent reads the project brief and outputs 3-5 clarifying questions for the user to answer *before* generation starts.
  - Implement the single-model provider abstraction.
  - Build the initial full-pipeline generation flow (PRD → SDD → Schema → API → Stories → Tasks).

### Phase 2: Diff-Aware Selective Regeneration Engine

**Objective:** Implement the core novelty of AgentFlow—the ability to compute diffs and regenerate only the affected downstream subgraph.

- **Graph Engine Enhancements:**
  - Implement the hashing mechanism for `artifact_sections`.
  - Build the diffing logic to identify changed sections on edits.
  - Implement the BFS-based `recompute_subgraph` algorithm to traverse `section_traces` and identify the affected subgraph.
- **Targeted Generation:**
  - Update agent prompts to accept diff summaries and prior content for continuity.
  - Wire the orchestrator to execute only the dirty nodes in topological order.
  - Implement versioning and rollback mechanisms in the database.

### Phase 3: Artifact-Specific Quality-Signal Router

**Objective:** Transition to a multi-provider setup where each artifact generation is routed to the most cost-effective and capable model based on structural quality signals.

- **Router Implementation:**
  - Expand the LLM provider abstraction to support multiple providers (e.g., OpenAI, Anthropic).
  - Implement the `Quality-Signal Router` decision engine.
  - Define the scoring logic for candidates based on historical performance and cost per token.
- **Quality Metrics & Logging:**
  - Implement the computation of structural quality signals post-generation (e.g., referential integrity for schemas, traceability for PRDs).
  - Store routing decisions and actual quality scores in the `generation_logs` to build the `historical_scores` feedback loop.

### Phase 4: Consistency Auditor Agent & Micro-Regeneration

**Objective:** Introduce continuous validation to detect cross-document semantic drift and trigger targeted fixes.

- **Auditor Implementation:**
  - Implement the `Consistency Auditor Agent` as a standalone LangGraph subgraph.
  - Define the specific structural validation rules (e.g., API endpoint ↔ DB schema field).
- **Drift Management:**
  - Create the `drift_records` table and logic to log detected inconsistencies.
  - Implement the micro-regeneration flow: isolating the discrepancy and triggering a minimal section-level regeneration.
  - Hook the auditor to run automatically after generation events and on a periodic schedule.

### Phase 5: Dashboard Development

**Objective:** Build the interactive web UI for visualization and interaction.

- **Frontend Foundation:**
  - Initialize the Next.js project.
  - Set up the project intake form (brief submission).
- **Graph & State Visualization:**
  - Integrate `React Flow` to render the dependency graph.
  - Implement real-time status updates via WebSockets (`fresh`, `stale`, `regenerating`, `drifted`).
- **Interactive Features:**
  - Build the Artifact Panel for viewing/editing section content and inline diffs.
  - Build the Drift Panel to manage, auto-fix, or dismiss drift records.
  - Build the Metrics Panel to visualize cost, latency, and quality charts.

### Phase 6: Evaluation Harness & Benchmarking

**Objective:** Validate the system against the predefined baselines (Single-LLM and Multi-agent without dependency tracking) using the 15-20 project briefs.

- **Harness Implementation:**
  - Build the `eval` module to automate pipeline runs across the test corpus.
  - Implement the scripted mid-project edit scenarios to test regeneration efficiency.
- **Data Collection & Reporting:**
  - Aggregate metrics (cost, latency, quality scores, drift percentage) into the `eval_runs` and `eval_results` tables.
  - Extend the dashboard to support side-by-side comparison of AgentFlow vs. baselines.

### Phase 7: Automated Code Generation, Local Storage & ZIP Export

**Objective:** Bridge the specification-to-code gap by adding a downstream Code Generator Agent that scaffolds runnable project files directly on local disk and provides one-click ZIP packaging.

- **Code Generator Agent (7th Node in DAG):**
  - Extend the LangGraph dependency graph: `PRD → SDD → DB_SCHEMA → API_SPEC → USER_STORIES → TASKS → CODE_GENERATION`.
  - Ingest the DB Schema (SQL DDL), API Specification (OpenAPI routes), and Task breakdown to generate complete application source code (backend models, API route handlers, frontend components, and project configuration).
- **Local Disk Storage (`generated_projects/<project_slug>/`):**
  - Scaffold generated repositories directly into a local folder on disk for immediate developer access in IDEs (VS Code / Cursor).
  - Implement selective diff-aware file patching: editing an upstream API route or DB table updates *only* the affected code file on disk rather than re-generating the whole codebase.
- **ZIP Export & Dashboard Action:**
  - Add backend streaming archive endpoint (`GET /projects/{project_id}/download-zip`) to package the active codebase on-the-fly.
  - Add an interactive **"📥 Download Project (.zip)"** button in the Next.js Dashboard.

---

## Verification Plan

### Automated Tests
- **Unit Tests:** `pytest` for graph traversal logic (affected subgraph computation), router scoring math, schema validation, and code scaffolding parser.
- **Integration Tests:** End-to-end API tests validating the REST endpoints for project creation, artifact updates, code generation, and ZIP streaming.
- **Evaluation Scripts:** The Phase 6 evaluation harness will serve as the system-level automated verification benchmark.

### Manual Verification
- Deploying the full stack via `docker-compose` locally.
- Submitting a sample project brief via the Next.js dashboard and verifying all 7 nodes execute.
- Inspecting the local `generated_projects/<project_slug>/` directory to verify source code files are created and runnable.
- Modifying an upstream artifact (e.g., API Spec) via the UI and visually verifying that only the affected downstream code files are patched.
- Downloading the `.zip` archive from the dashboard and extracting it to run locally.

