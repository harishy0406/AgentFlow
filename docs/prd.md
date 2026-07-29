# Product Requirements Document (PRD)
## AgentFlow — Dependency-Aware Selective Regeneration for Multi-Agent Software Engineering Artifact Generation

| | |
|---|---|
| **Author** | M Harish Gautham |
| **Document Type** | Product Requirements Document |
| **Version** | 1.0 |
| **Status** | Draft |

---

## 1. Executive Summary

AgentFlow is an adaptive multi-agent workflow orchestration platform that automates the generation, synchronization, and evolution of software engineering artifacts — PRDs, Software Design Documents (SDDs), database schemas, API specifications, user stories, and task breakdowns.

Unlike existing multi-agent LLM frameworks (MetaGPT, ChatDev, ALMAS) that treat requirement changes as a trigger for full-pipeline regeneration, AgentFlow models the artifact lifecycle as a **typed dependency graph** and performs **diff-aware selective regeneration**, updating only the artifacts actually affected by a change. It further introduces **artifact-specific quality-signal routing** to pick the right LLM for each document type, and a **Consistency Auditor Agent** that continuously detects and repairs cross-document drift.

The result is a system that is cheaper, faster, and more consistent than "all-or-nothing" multi-agent documentation pipelines, particularly in real-world settings where requirements change frequently mid-project.

---

## 2. Problem Statement

Software teams generate a chain of interdependent artifacts during the planning phase of a project: a PRD leads to an SDD, which leads to a database schema, which leads to an API specification, which leads to user stories, which leads to a task breakdown. In practice:

- These artifacts are authored manually and disconnected from one another, so a change in one document (e.g., a new requirement in the PRD) is not systematically propagated downstream.
- Existing multi-agent LLM systems that *do* automate this pipeline (MetaGPT, ChatDev) regenerate the **entire** document chain from scratch whenever anything changes — burning tokens, adding latency, and risking semantic drift between old and new content that wasn't touched.
- Code-focused multi-agent frameworks such as ALMAS and Meta-RAG solve an adjacent problem (AST-based codebase compression for bug localization) but do not address upstream documentation artifacts at all.
- LLM routing in current systems is based on generic prompt difficulty or token length, not on the structural quality needs of a specific artifact type (e.g., a database schema needs referential-integrity correctness; a PRD needs requirement traceability).
- No existing system continuously audits cross-document consistency (e.g., an API endpoint with no corresponding database field, or a user story with no traceable PRD requirement) — drift is discovered late, usually by a human reviewer.

**Core problem:** There is no system that treats software engineering artifacts as a structured, versioned, interdependent graph and regenerates only what a change actually affects, while actively guarding against cross-document drift.

---

## 3. Goals & Objectives

1. **Reduce regeneration cost and latency** for mid-project requirement changes by regenerating only affected downstream artifacts instead of the full document chain.
2. **Improve artifact quality per dollar spent** by routing each artifact type to the LLM provider best suited to its structural quality signal, rather than a single fixed model or a generic difficulty router.
3. **Minimize cross-artifact semantic drift** through continuous, automated structural auditing and targeted micro-regeneration.
4. **Provide visibility** into the artifact dependency graph and the state of each document via an interactive dashboard.
5. **Produce a reproducible evaluation** comparing AgentFlow against (a) a single-LLM baseline and (b) a standard multi-agent pipeline without dependency tracking, across cost, latency, quality, drift, and regeneration efficiency.

---

## 4. Target Users / Personas

| Persona | Description | Needs |
|---|---|---|
| **Startup Founder / Solo Builder** | Needs to go from idea to a full requirements + design package quickly | Fast, cheap, consistent documentation generation |
| **Product Manager** | Owns the PRD and needs downstream artifacts to stay in sync as requirements evolve | Change propagation without manual re-writing everything |
| **Tech Lead / Architect** | Owns SDD, schema, and API spec; needs confidence these stay consistent | Automated drift detection, traceability |
| **Engineering Team** | Consumes user stories and task breakdowns | Up-to-date, accurate task lists reflecting the latest requirements |
| **Research Evaluator** | Benchmarking multi-agent documentation systems | Reproducible cost/latency/quality/drift metrics |

---

## 5. Key Novelty (Differentiators)

1. **Typed Dependency-Graph-Aware Selective Regeneration** — Artifacts are nodes in a typed directed graph (PRD → SDD → Database Schema → API Spec → User Stories → Tasks). A requirement change triggers a diff-aware subgraph recomputation that touches only affected downstream nodes, instead of full-pipeline regeneration used by MetaGPT/ChatDev, and unlike ALMAS/Meta-RAG which only operate on source code via AST compression.
2. **Artifact-Type-Specific Quality-Signal Routing** — Instead of routing on generic prompt difficulty (as surveyed in Yang et al.), AgentFlow's Decision Engine scores each artifact type on a domain-specific structural signal (referential integrity for schemas, requirement-traceability coverage for PRDs, endpoint completeness for API specs) and routes to the most cost-effective capable model accordingly.
3. **Continuous Cross-Artifact Consistency Auditing** — A dedicated Auditor Agent continuously runs graph-structural validation across the whole document set (e.g., API endpoint ↔ DB field ↔ PRD requirement), detects drift, and triggers targeted micro-regeneration — addressing a gap neither Tawosi et al. (single-plan LTL verification) nor Hutter & Pradel (agent trajectory debugging) cover.

---

## 6. Scope

### 6.1 In Scope
- Multi-agent generation pipeline for six artifact types: PRD, SDD, Database Schema, API Specification, User Stories, Task Breakdown.
- Typed dependency graph model with diff-aware subgraph recomputation.
- Quality-signal-based model routing across at least two LLM providers.
- Consistency Auditor Agent with structural drift detection rules.
- Web dashboard (Next.js + React Flow) for graph visualization, artifact editing, and regeneration triggers.
- Versioning of every artifact node.
- Evaluation harness across 15–20 project briefs comparing AgentFlow to two baselines.

### 6.2 Out of Scope (v1)
- Code generation / implementation of the actual software product being documented.
- IDE plugins or CI/CD integration.
- Multi-user real-time collaborative editing (single-user editing only in v1).
- Support for artifact types beyond the six listed (e.g., test plans, deployment runbooks) — reserved for future work.
- On-premise/self-hosted LLM fine-tuning.

---

## 7. Functional Requirements

### 7.1 Artifact Generation
- FR-1: The system shall generate a PRD from a free-text project brief.
- FR-2: The system shall generate an SDD conditioned on the current PRD.
- FR-3: The system shall generate a Database Schema conditioned on the current SDD.
- FR-4: The system shall generate an API Specification conditioned on the current Database Schema and SDD.
- FR-5: The system shall generate User Stories conditioned on the current PRD and API Specification.
- FR-6: The system shall generate a Task Breakdown conditioned on User Stories and API Specification.

### 7.2 Dependency Graph & Selective Regeneration
- FR-7: The system shall represent each artifact as a typed node in a directed dependency graph with explicit edges to downstream artifacts.
- FR-8: When a user edits/updates any node, the system shall compute a diff and identify the minimal subgraph of downstream nodes affected.
- FR-9: The system shall regenerate only the identified affected subgraph, leaving unaffected nodes untouched and their version history intact.
- FR-10: The system shall version every regeneration and allow rollback to a previous artifact version.

### 7.3 Quality-Signal Routing
- FR-11: The system shall compute a structural quality signal per artifact type (e.g., referential integrity score for schemas, requirement-traceability coverage for PRDs, endpoint-completeness score for API specs).
- FR-12: The Decision Engine shall select an LLM provider/model per generation task based on the artifact type's quality-signal requirements and a cost/capability trade-off.
- FR-13: The system shall log the routing decision and resulting quality signal for every generation call.

### 7.4 Consistency Auditing
- FR-14: The Auditor Agent shall continuously (or on-demand) validate structural consistency across artifact pairs (e.g., API endpoint ↔ DB schema field ↔ PRD requirement).
- FR-15: On detecting drift, the Auditor Agent shall isolate the specific discrepancy and trigger a targeted micro-regeneration task scoped to the smallest necessary artifact section.
- FR-16: The system shall maintain a drift log showing detected inconsistencies, their resolution, and time-to-resolution.

### 7.5 Dashboard & Visualization
- FR-17: The dashboard shall render the dependency graph interactively (React Flow), showing node status (fresh, stale, regenerating, drifted).
- FR-18: Users shall be able to view, edit, and manually trigger regeneration of any artifact node from the dashboard.
- FR-19: The dashboard shall display cost, latency, and quality-signal metrics per artifact and per project.

### 7.6 Evaluation Harness
- FR-20: The system shall support running the full pipeline against a batch of project briefs and recording cost (tokens/USD), latency, artifact quality, cross-document drift %, and regeneration efficiency versus baselines.

---

## 8. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Performance** | Selective regeneration of a single affected node should complete in under the time of a full-pipeline baseline regeneration for the same edit, with a target of ≥40% latency reduction on typical mid-project edits. |
| **Cost Efficiency** | Token/cost usage for a selective regeneration should be measurably lower than full-pipeline regeneration on the same test set. |
| **Reliability** | The system shall persist all artifact versions and graph state durably (PostgreSQL); no data loss on process restart. |
| **Consistency** | The Auditor Agent shall run drift checks after every regeneration event automatically. |
| **Extensibility** | New artifact types and new LLM providers should be addable without core graph-engine changes. |
| **Observability** | All agent calls, routing decisions, and audit results shall be logged and queryable. |
| **Security** | API keys and provider credentials shall never be exposed to the client; all secrets managed server-side. |

---

## 9. User Stories

- As a **product manager**, I want to update a single requirement in the PRD and have only the truly affected downstream documents regenerate, so that I don't lose unrelated edits made by my team.
- As a **tech lead**, I want the system to flag when an API endpoint has no matching database field, so that I catch integration bugs before development starts.
- As a **founder**, I want to generate a full requirements package from a one-paragraph idea, so I can move fast without hiring a technical writer.
- As a **researcher**, I want to run the same set of project briefs through AgentFlow and two baselines, so I can compare cost, latency, quality, and drift objectively.
- As a **team member**, I want a visual graph of how documents depend on each other, so I understand the impact of any requested change before I request it.

---

## 10. Success Metrics / Evaluation Plan

AgentFlow will be evaluated against:
1. A **single-LLM generation baseline** (one model generates all artifacts sequentially, full regeneration on every change).
2. A **standard multi-agent pipeline without dependency tracking** (multiple specialized agents, but full-pipeline regeneration on every change).

Across **15–20 diverse project briefs**, the following will be measured:

| Metric | Description | Target |
|---|---|---|
| **Execution Cost** | Tokens and USD spent per full pipeline run and per mid-project edit | Selective regeneration should cost significantly less than both baselines on edits |
| **Latency** | Wall-clock time to produce/update artifacts | Selective regeneration should be faster than full-pipeline baselines |
| **Artifact Quality** | Expert rubric scoring + semantic similarity metrics against reference artifacts | Comparable or better quality than baselines |
| **Cross-Document Consistency Drift (%)** | Rate of detected structural inconsistencies across the document set | Lower drift than both baselines |
| **Regeneration Efficiency** | Ratio of nodes regenerated vs. total nodes, following a mid-project requirement change | Substantially fewer nodes regenerated than full-pipeline baselines for the same edit |

---

## 11. Assumptions & Constraints

- Access to at least two LLM providers (e.g., Anthropic, OpenAI) is available for routing experiments.
- Project briefs used for evaluation are text-based and of moderate complexity (small-to-medium software products).
- The system assumes a single active editor per project in v1 (no real-time multi-user conflict resolution).
- Vector storage (Pinecone) is available for context retrieval across artifacts.

## 12. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Dependency graph misclassifies an edit's blast radius (under- or over-regeneration) | Stale or unnecessarily regenerated artifacts | Conservative diff heuristics + Auditor Agent as a safety net |
| Quality-signal metrics don't correlate with actual human-perceived quality | Router makes poor model choices | Validate signals against expert rubric scores during evaluation |
| LLM provider cost/availability changes | Budget and latency targets missed | Abstract provider layer; router can fall back to alternate providers |
| Consistency Auditor produces false positives | Unnecessary micro-regenerations, wasted cost | Tunable confidence thresholds; human-in-the-loop override on the dashboard |

## 13. Milestones / Roadmap

| Phase | Deliverable |
|---|---|
| Phase 1 | Core data model, typed dependency graph, single-model generation pipeline (no routing/auditing) |
| Phase 2 | Diff-aware selective regeneration engine |
| Phase 3 | Artifact-specific quality-signal router (multi-provider) |
| Phase 4 | Consistency Auditor Agent + micro-regeneration |
| Phase 5 | Dashboard (Next.js + React Flow) |
| Phase 6 | Evaluation harness + benchmark run across 15–20 project briefs + report |

## 14. Glossary

- **Typed Dependency Graph** — A directed graph where each node is a software artifact of a specific type, and edges represent generation dependency (e.g., SDD depends on PRD).
- **Selective Regeneration** — Regenerating only the subgraph of artifacts affected by a change, rather than the whole pipeline.
- **Quality-Signal Router** — The Decision Engine component that picks an LLM per artifact type based on structural quality metrics.
- **Consistency Drift** — A structural mismatch between two related artifacts (e.g., an API endpoint with no backing database field).
- **Micro-Regeneration** — A targeted regeneration of a small section of an artifact, triggered by the Auditor Agent to fix detected drift.
