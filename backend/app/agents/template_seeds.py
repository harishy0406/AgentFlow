"""
Template Seed Data Engine — AgentFlow Starter Architecture Presets

Provides complete, pre-configured seed definitions for all 4 starter templates:
1. AI Code Reviewer (DevOps & AI)
2. FinTech Escrow API (FinTech & Payments)
3. HIPAA Telehealth Suite (Healthcare & MedTech)
4. Multi-Vendor Marketplace (E-Commerce & Retail)

Also includes dynamic project synthesis for custom briefs to guarantee
100% offline, demo-ready project initialization without external LLM dependencies.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .. import models
from .graph_engine import compute_content_hash, TOPOLOGICAL_ORDER
from .scaffolder import scaffold_project_files, sanitize_project_slug


# ---------------------------------------------------------------------------
# Template Definitions Catalog
# ---------------------------------------------------------------------------

TEMPLATE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "ai_code_reviewer": {
        "id": "ai_code_reviewer",
        "aliases": ["saas_ai_reviewer", "ai-code-reviewer", "ai code reviewer", "code reviewer"],
        "title": "AI Code Reviewer",
        "tag": "DevOps & AI",
        "workspace_name": "DevOps & AI Systems",
        "brief": "Build an enterprise AI Code Reviewer that automatically parses GitHub pull requests, performs static AST analysis, checks for OWASP vulnerabilities, and posts inline suggestions with benchmarked test cases.",
        "clarifications": "Questions:\n1. Which VCS platforms should be supported (GitHub Cloud, GitHub Enterprise Server, GitLab)?\n2. What static analysis rule standards should be enabled (OWASP Top 10, CWE/SANS 25, PEP 8)?\n3. What is the expected PR volume and latency SLA for inline review suggestions?\n4. Should the reviewer generate automated benchmark tests and inline autofix git patches?\n\nAnswers:\n1. Target GitHub Cloud and GitHub Enterprise Server with Webhook and App integration.\n2. Enforce OWASP Top 10 and AST static analysis with customizable severity threshold.\n3. SLA < 90 seconds per pull request with Redis caching and concurrency up to 500 PRs/hour.\n4. Yes, provide inline code diff suggestions and automated pytest regression tests.",
        "quality_scores": {
            "PRD": 96.5,
            "SDD": 94.0,
            "DB_SCHEMA": 98.0,
            "API_SPEC": 95.5,
            "USER_STORIES": 93.0,
            "TASKS": 91.5,
            "CODE_GENERATION": 95.0,
        },
        "artifacts": {
            "PRD": {
                "executive_summary": (
                    "# AI Code Reviewer — Product Requirements Document\n\n"
                    "## Executive Summary\n"
                    "The Enterprise AI Code Reviewer is an autonomous, high-throughput code review bot designed "
                    "for modern engineering teams. It integrates into GitHub pull request workflows via GitHub Webhooks "
                    "and the GitHub Checks API, performing abstract syntax tree (AST) static analysis, OWASP Top 10 security scanning, "
                    "and generative AI code quality reviews. It posts contextual inline suggestions with ready-to-merge git diffs and benchmarked test cases."
                ),
                "user_personas": (
                    "## Target Personas\n\n"
                    "1. **Staff Software Engineer / Tech Lead**: Needs consistent code reviews that catch subtle architectural defects, concurrency hazards, and anti-patterns before merging.\n"
                    "2. **AppSec Specialist**: Demands strict enforcement of OWASP security standards, secret leakage prevention, and SQL injection / XSS detection.\n"
                    "3. **Junior / Mid-level Developer**: Benefits from educational inline explanations and ready-to-apply diff recommendations.\n"
                    "4. **Engineering Manager**: Requires metrics on code review cycle times, defect escape rates, and automated test coverage trends."
                ),
                "functional_requirements": (
                    "## Functional Requirements\n\n"
                    "- **FR-1 Webhook Ingestion**: Ingest `pull_request.opened`, `pull_request.synchronize`, and `pull_request.reopened` payloads with HMAC-SHA256 signature verification.\n"
                    "- **FR-2 AST Parser Engine**: Parse Python, TypeScript, and Go source files into AST syntax nodes to extract modified functions and call graphs.\n"
                    "- **FR-3 Security & Rule Scanner**: Match code against OWASP Top 10 rules, credential regex patterns, and insecure dependency imports.\n"
                    "- **FR-4 Contextual Inline Reviews**: Post GitHub review comments at exact file lines with markdown code suggestions.\n"
                    "- **FR-5 Test Case Generator**: Generate executable pytest and Jest test suites for untested branches.\n"
                    "- **FR-6 False Positive Management**: Enable engineers to dismiss or suppress rules via inline `# af:ignore` comments."
                ),
                "non_functional_requirements": (
                    "## Non-Functional Requirements\n\n"
                    "- **Latency**: Deliver full pull request analysis within 60 seconds (p95) for pull requests up to 1,500 lines of diff.\n"
                    "- **Availability**: 99.95% uptime with graceful degradation to static rule checks if LLM providers encounter rate limits.\n"
                    "- **Security**: Zero data retention of private repository code; ephemeral execution sandbox with memory-only diff processing."
                )
            },
            "SDD": {
                "architecture_overview": (
                    "# AI Code Reviewer — System Design Document\n\n"
                    "## Architecture Topology\n\n"
                    "```mermaid\n"
                    "flowchart TD\n"
                    "  GH[GitHub Cloud / Enterprise] -->|Webhooks HMAC| GW[Ingress API Gateway]\n"
                    "  GW -->|Push Job| Q[Redis Celery Queue]\n"
                    "  Q --> W1[Worker: AST Parser]\n"
                    "  Q --> W2[Worker: OWASP Rule Engine]\n"
                    "  W1 & W2 --> AGG[Review Aggregator & LLM Reasoner]\n"
                    "  AGG --> DB[(PostgreSQL 16)]\n"
                    "  AGG -->|GitHub REST API| GH\n"
                    "```\n\n"
                    "The system follows an asynchronous, queue-decoupled microservices pattern. Ingress requests are authenticated via "
                    "GitHub App HMAC tokens, pushed into Redis queues, and evaluated concurrently by dedicated worker pods."
                ),
                "component_design": (
                    "## Component Specifications\n\n"
                    "1. **Ingress Gateway (FastAPI)**: Receives webhook payloads, validates HMAC headers, and enqueues jobs in < 15ms.\n"
                    "2. **AST Parser Engine**: Native Python `ast` module and Tree-sitter parsers isolate semantic change blocks.\n"
                    "3. **Security Audit Daemon**: Evaluates Bandit, Semgrep, and OWASP rule patterns against diff chunks.\n"
                    "4. **AI Reasoning Synthesizer**: Uses multi-model orchestration (Claude 3.5 Sonnet / Haiku) to evaluate code clarity and generate diffs.\n"
                    "5. **GitHub API Dispatcher**: Batches inline comments into a single cohesive GitHub PR review summary."
                ),
                "data_persistence": (
                    "## Data Persistence Strategy\n\n"
                    "PostgreSQL 16 stores audit logs, repository configs, rule sets, and review run histories. "
                    "Redis 7.2 serves as the job queue broker and token bucket rate limiter."
                )
            },
            "DB_SCHEMA": {
                "relational_ddl": (
                    "-- ==========================================================================\n"
                    "-- AI Code Reviewer Database DDL (PostgreSQL 16)\n"
                    "-- ==========================================================================\n\n"
                    "CREATE TABLE IF NOT EXISTS users (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    github_username VARCHAR(100) NOT NULL UNIQUE,\n"
                    "    email VARCHAR(255) NOT NULL UNIQUE,\n"
                    "    role VARCHAR(50) NOT NULL DEFAULT 'developer',\n"
                    "    is_active BOOLEAN NOT NULL DEFAULT TRUE,\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS repositories (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,\n"
                    "    name VARCHAR(200) NOT NULL,\n"
                    "    full_name VARCHAR(255) NOT NULL UNIQUE,\n"
                    "    default_branch VARCHAR(100) NOT NULL DEFAULT 'main',\n"
                    "    is_private BOOLEAN NOT NULL DEFAULT FALSE,\n"
                    "    settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS pull_requests (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,\n"
                    "    pr_number INTEGER NOT NULL,\n"
                    "    title VARCHAR(500) NOT NULL,\n"
                    "    author VARCHAR(100) NOT NULL,\n"
                    "    head_sha VARCHAR(40) NOT NULL,\n"
                    "    base_sha VARCHAR(40) NOT NULL,\n"
                    "    status VARCHAR(50) NOT NULL DEFAULT 'open',\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,\n"
                    "    UNIQUE(repository_id, pr_number)\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS review_runs (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    pull_request_id UUID NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,\n"
                    "    commit_sha VARCHAR(40) NOT NULL,\n"
                    "    status VARCHAR(50) NOT NULL DEFAULT 'completed',\n"
                    "    files_analyzed INTEGER NOT NULL DEFAULT 0,\n"
                    "    findings_count INTEGER NOT NULL DEFAULT 0,\n"
                    "    quality_score NUMERIC(5,2) NOT NULL DEFAULT 100.0,\n"
                    "    execution_time_ms INTEGER NOT NULL DEFAULT 0,\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS vulnerability_findings (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    review_run_id UUID NOT NULL REFERENCES review_runs(id) ON DELETE CASCADE,\n"
                    "    rule_id VARCHAR(100) NOT NULL,\n"
                    "    file_path VARCHAR(500) NOT NULL,\n"
                    "    line_number INTEGER NOT NULL,\n"
                    "    severity VARCHAR(20) NOT NULL, -- 'info', 'warning', 'high', 'critical'\n"
                    "    title VARCHAR(255) NOT NULL,\n"
                    "    description TEXT NOT NULL,\n"
                    "    suggested_diff TEXT,\n"
                    "    status VARCHAR(50) NOT NULL DEFAULT 'open'\n"
                    ");\n\n"
                    "CREATE INDEX IF NOT EXISTS idx_repo_owner ON repositories(owner_id);\n"
                    "CREATE INDEX IF NOT EXISTS idx_pr_repo_num ON pull_requests(repository_id, pr_number);\n"
                    "CREATE INDEX IF NOT EXISTS idx_review_pr ON review_runs(pull_request_id);\n"
                    "CREATE INDEX IF NOT EXISTS idx_findings_run ON vulnerability_findings(review_run_id);"
                ),
                "schema_summary": (
                    "## Relational Entity Model\n"
                    "Normalized 3NF relational model supporting multi-tenant GitHub repository analysis with cascade deletion "
                    "and optimized indexes for sub-millisecond status lookups."
                )
            },
            "API_SPEC": {
                "openapi_yaml": (
                    "openapi: 3.0.3\n"
                    "info:\n"
                    "  title: AI Code Reviewer API\n"
                    "  version: 1.0.0\n"
                    "  description: Enterprise API for automated pull request code analysis and vulnerability scanning.\n"
                    "paths:\n"
                    "  /api/v1/health:\n"
                    "    get:\n"
                    "      summary: System Health & Daemon Status\n"
                    "      responses:\n"
                    "        '200':\n"
                    "          description: Service is healthy\n"
                    "          content:\n"
                    "            application/json:\n"
                    "              schema:\n"
                    "                type: object\n"
                    "                properties:\n"
                    "                  status:\n"
                    "                    type: string\n"
                    "                    example: ok\n"
                    "  /api/v1/reviews:\n"
                    "    post:\n"
                    "      summary: Trigger On-Demand Pull Request Review\n"
                    "      requestBody:\n"
                    "        required: true\n"
                    "        content:\n"
                    "          application/json:\n"
                    "            schema:\n"
                    "              type: object\n"
                    "              required: [repository, pr_number, commit_sha]\n"
                    "              properties:\n"
                    "                repository:\n"
                    "                  type: string\n"
                    "                  example: org/backend-service\n"
                    "                pr_number:\n"
                    "                  type: integer\n"
                    "                  example: 142\n"
                    "                commit_sha:\n"
                    "                  type: string\n"
                    "                  example: 7f8a9b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a\n"
                    "      responses:\n"
                    "        '202':\n"
                    "          description: Review job enqueued successfully\n"
                    "  /api/v1/reviews/{id}:\n"
                    "    get:\n"
                    "      summary: Get Review Run Details and Findings\n"
                    "      parameters:\n"
                    "        - name: id\n"
                    "          in: path\n"
                    "          required: true\n"
                    "          schema:\n"
                    "            type: string\n"
                    "            format: uuid\n"
                    "      responses:\n"
                    "        '200':\n"
                    "          description: Review run findings summary\n"
                    "  /api/v1/webhooks/github:\n"
                    "    post:\n"
                    "      summary: GitHub Webhook Ingress Endpoint\n"
                    "      responses:\n"
                    "        '200':\n"
                    "          description: Webhook acknowledged\n"
                )
            },
            "USER_STORIES": {
                "stories_list": (
                    "# AI Code Reviewer — User Stories\n\n"
                    "### US-1: Automated PR Security Triage\n"
                    "**As a** DevOps Engineer,  \n"
                    "**I want** every opened pull request to be scanned for OWASP vulnerabilities automatically,  \n"
                    "**So that** security regressions never reach the staging environment.\n\n"
                    "```gherkin\n"
                    "Scenario: SQL Injection detection\n"
                    "  Given a developer opens a PR containing raw string concatenation in a SQL query\n"
                    "  When the AI Code Reviewer evaluates the diff\n"
                    "  Then it marks the check run as 'action_required'\n"
                    "  And it posts an inline comment suggesting parameterized queries with code diff\n"
                    "```\n\n"
                    "### US-2: Performance & AST Complexity Warnings\n"
                    "**As a** Senior Backend Engineer,  \n"
                    "**I want** notifications on high cyclomatic complexity and O(N^2) loops inside request handlers,  \n"
                    "**So that** API response latency stays under our 50ms SLA.\n\n"
                    "### US-3: Automated Regression Test Generation\n"
                    "**As a** Full-Stack Developer,  \n"
                    "**I want** the bot to propose unit tests for newly added functions,  \n"
                    "**So that** our team code coverage target of 85% is maintained without extra manual boilerplate."
                )
            },
            "TASKS": {
                "tasks_list": (
                    "# AI Code Reviewer — Engineering Task DAG\n\n"
                    "- [x] **TASK-01**: Initialize FastAPI application skeleton with PostgreSQL async session pool. *(Estimate: 1 day)*\n"
                    "- [x] **TASK-02**: Implement GitHub Webhook HMAC-SHA256 signature verification middleware. *(Estimate: 1 day)*\n"
                    "- [x] **TASK-03**: Build Tree-sitter and Python AST diff chunk extractor service. *(Estimate: 2 days)*\n"
                    "- [x] **TASK-04**: Implement OWASP Top 10 rule pattern matcher (SQLi, XSS, SSRF, Hardcoded Secrets). *(Estimate: 3 days)*\n"
                    "- [x] **TASK-05**: Integrate Multi-Model LLM provider routing for contextual diff suggestions. *(Estimate: 2 days)*\n"
                    "- [x] **TASK-06**: Implement GitHub Checks API publisher for inline pull request comments. *(Estimate: 2 days)*\n"
                    "- [x] **TASK-07**: Configure Redis job queue and Celery worker pool for horizontal scaling. *(Estimate: 2 days)*\n"
                    "- [x] **TASK-08**: Build automated unit test suite with 90%+ branch coverage. *(Estimate: 2 days)*"
                )
            },
            "CODE_GENERATION": {
                "code_bundle": (
                    "### File: backend/main.py\n"
                    "```python\n"
                    "from fastapi import FastAPI, HTTPException, Request, Depends, status\n"
                    "from fastapi.middleware.cors import CORSMiddleware\n"
                    "from pydantic import BaseModel, Field\n"
                    "from typing import List, Optional\n"
                    "import hmac\n"
                    "import hashlib\n"
                    "import os\n\n"
                    "app = FastAPI(\n"
                    "    title='AI Code Reviewer Engine',\n"
                    "    version='1.0.0',\n"
                    "    description='Autonomous AST & OWASP Code Reviewer Service'\n"
                    ")\n\n"
                    "app.add_middleware(\n"
                    "    CORSMiddleware,\n"
                    "    allow_origins=['*'],\n"
                    "    allow_credentials=True,\n"
                    "    allow_methods=['*'],\n"
                    "    allow_headers=['*'],\n"
                    ")\n\n"
                    "@app.get('/api/v1/health')\n"
                    "def health_check():\n"
                    "    return {\n"
                    "        'status': 'healthy',\n"
                    "        'service': 'ai-code-reviewer',\n"
                    "        'version': '1.0.0',\n"
                    "        'ast_engine': 'tree-sitter-ready'\n"
                    "    }\n\n"
                    "class ReviewRequest(BaseModel):\n"
                    "    repository: str = Field(..., example='octocat/hello-world')\n"
                    "    pr_number: int = Field(..., example=42)\n"
                    "    commit_sha: str = Field(..., example='6dcb09b5b57875f334f61aebed695e2e4193db5e')\n\n"
                    "class ReviewFinding(BaseModel):\n"
                    "    file_path: str\n"
                    "    line_number: int\n"
                    "    severity: str\n"
                    "    title: str\n"
                    "    description: str\n"
                    "    suggested_diff: Optional[str] = None\n\n"
                    "@app.post('/api/v1/reviews', status_code=status.HTTP_202_ACCEPTED)\n"
                    "def enqueue_review(req: ReviewRequest):\n"
                    "    # Simulates asynchronous review queue\n"
                    "    return {\n"
                    "        'job_id': 'rev_job_9941a87',\n"
                    "        'repository': req.repository,\n"
                    "        'pr_number': req.pr_number,\n"
                    "        'status': 'queued'\n"
                    "    }\n"
                    "```\n\n"
                    "### File: backend/models.py\n"
                    "```python\n"
                    "from sqlalchemy import Column, String, Integer, Boolean, Numeric, DateTime, ForeignKey\n"
                    "from sqlalchemy.dialects.postgresql import UUID\n"
                    "from sqlalchemy.orm import declarative_base, relationship\n"
                    "import uuid\n"
                    "from datetime import datetime, timezone\n\n"
                    "Base = declarative_base()\n\n"
                    "class Repository(Base):\n"
                    "    __tablename__ = 'repositories'\n"
                    "    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)\n"
                    "    full_name = Column(String(255), unique=True, nullable=False)\n"
                    "    default_branch = Column(String(100), default='main')\n"
                    "    is_active = Column(Boolean, default=True)\n"
                    "    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))\n\n"
                    "class ReviewRun(Base):\n"
                    "    __tablename__ = 'review_runs'\n"
                    "    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)\n"
                    "    repo_id = Column(UUID(as_uuid=True), ForeignKey('repositories.id'))\n"
                    "    pr_number = Column(Integer, nullable=False)\n"
                    "    quality_score = Column(Numeric(5, 2), default=98.0)\n"
                    "    findings_count = Column(Integer, default=0)\n"
                    "```\n\n"
                    "### File: backend/services/ast_analyzer.py\n"
                    "```python\n"
                    "import ast\n"
                    "from typing import List, Dict, Any\n\n"
                    "class ASTSecurityAnalyzer(ast.NodeVisitor):\n"
                    "    def __init__(self):\n"
                    "        self.findings: List[Dict[str, Any]] = []\n\n"
                    "    def visit_Call(self, node):\n"
                    "        # Detect raw cursor.execute string formats\n"
                    "        if isinstance(node.func, ast.Attribute) and node.func.attr == 'execute':\n"
                    "            if node.args and isinstance(node.args[0], (ast.BinOp, ast.JoinedStr)):\n"
                    "                self.findings.append({\n"
                    "                    'rule': 'OWASP_A03_INJECTION',\n"
                    "                    'line': node.lineno,\n"
                    "                    'severity': 'critical',\n"
                    "                    'message': 'Potential SQL injection: unparameterized query execution detected.'\n"
                    "                })\n"
                    "        self.generic_visit(node)\n"
                    "```\n\n"
                    "### File: requirements.txt\n"
                    "```text\n"
                    "fastapi>=0.110.0\n"
                    "uvicorn>=0.28.0\n"
                    "pydantic>=2.6.0\n"
                    "sqlalchemy>=2.0.28\n"
                    "psycopg2-binary>=2.9.9\n"
                    "redis>=5.0.2\n"
                    "pytest>=8.0.0\n"
                    "requests>=2.31.0\n"
                    "```\n\n"
                    "### File: README.md\n"
                    "```markdown\n"
                    "# AI Code Reviewer\n"
                    "Autonomous GitHub pull request analysis bot with AST static scanning and OWASP security checks.\n"
                    "```\n"
                )
            }
        }
    },

    "fintech_escrow": {
        "id": "fintech_escrow",
        "aliases": ["fintech-escrow", "fintech escrow", "escrow api"],
        "title": "FinTech Escrow API",
        "tag": "FinTech",
        "workspace_name": "FinTech & Payments Group",
        "brief": "Design a fault-tolerant multi-party escrow platform for freelance marketplaces. Requires milestone escrow holding, Stripe Connect payouts, dual-entry accounting ledgers, and KYC/AML verification workflows.",
        "clarifications": "Questions:\n1. Which Stripe Connect account hierarchy is required (Express, Custom, Standard)?\n2. What escrow milestone release triggers and dispute resolution timelines apply?\n3. What dual-entry ledger currency constraints and rounding rules must be observed?\n4. What regulatory reporting (FinCEN, 1099-K, SOC2) and KYC verification levels apply?\n\nAnswers:\n1. Stripe Connect Custom Accounts with platform white-label payout routing.\n2. Milestone releases trigger on client approval or 14-day auto-settlement with 7-day dispute window.\n3. Immutable double-entry book balancing with integer-cent storage (USD, EUR, GBP).\n4. Automated Stripe Identity KYC verification and compliance audit trail.",
        "quality_scores": {
            "PRD": 98.0,
            "SDD": 96.5,
            "DB_SCHEMA": 99.0,
            "API_SPEC": 97.0,
            "USER_STORIES": 94.5,
            "TASKS": 93.0,
            "CODE_GENERATION": 96.0,
        },
        "artifacts": {
            "PRD": {
                "executive_summary": (
                    "# FinTech Escrow API — Product Requirements Document\n\n"
                    "## Executive Summary\n"
                    "The Multi-Party Escrow API provides programmatic custody and milestone-based disbursement of funds "
                    "for high-value freelance and B2B contract transactions. Featuring double-entry accounting ledgers, "
                    "Stripe Connect Custom account payouts, dispute arbitration workflows, and automated KYC/AML verification."
                ),
                "functional_requirements": (
                    "## Core Capabilities\n"
                    "- **FR-1 Milestone Holding**: Hold funds in platform escrow until designated milestones are verified.\n"
                    "- **FR-2 Immutable Ledger**: Every debit has an exact matching credit; total ledger sum always equals zero.\n"
                    "- **FR-3 Stripe Payout Routing**: Seamless transfer to contractor accounts via Stripe Connect Transfers API.\n"
                    "- **FR-4 Dispute Mediation**: Frozen balances with evidence submission and arbitrator release endpoints."
                )
            },
            "SDD": {
                "architecture_overview": (
                    "# FinTech Escrow API — System Architecture\n\n"
                    "```mermaid\n"
                    "sequenceDiagram\n"
                    "  autonumber\n"
                    "  Client ->> EscrowAPI: Fund Milestone ($5,000)\n"
                    "  EscrowAPI ->> Stripe: Create PaymentIntent (Capture)\n"
                    "  Stripe -->> EscrowAPI: Payment Captured\n"
                    "  EscrowAPI ->> Ledger: Credit EscrowLiability / Debit PlatformCash\n"
                    "  Freelancer ->> EscrowAPI: Submit Deliverables\n"
                    "  Client ->> EscrowAPI: Approve Milestone\n"
                    "  EscrowAPI ->> Stripe: Transfer to Connected Account\n"
                    "  EscrowAPI ->> Ledger: Debit EscrowLiability / Credit ContractorPayable\n"
                    "```\n"
                )
            },
            "DB_SCHEMA": {
                "relational_ddl": (
                    "CREATE TABLE IF NOT EXISTS accounts (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    user_id UUID NOT NULL,\n"
                    "    account_type VARCHAR(50) NOT NULL, -- 'client', 'freelancer', 'platform'\n"
                    "    stripe_account_id VARCHAR(100),\n"
                    "    currency VARCHAR(3) NOT NULL DEFAULT 'USD',\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS escrow_contracts (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    client_account_id UUID NOT NULL REFERENCES accounts(id),\n"
                    "    freelancer_account_id UUID NOT NULL REFERENCES accounts(id),\n"
                    "    title VARCHAR(255) NOT NULL,\n"
                    "    total_amount_cents BIGINT NOT NULL,\n"
                    "    status VARCHAR(50) NOT NULL DEFAULT 'funded',\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS milestones (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    contract_id UUID NOT NULL REFERENCES escrow_contracts(id) ON DELETE CASCADE,\n"
                    "    title VARCHAR(255) NOT NULL,\n"
                    "    amount_cents BIGINT NOT NULL,\n"
                    "    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- 'pending', 'funded', 'released', 'disputed'\n"
                    "    due_date TIMESTAMP WITH TIME ZONE,\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS ledger_entries (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    transaction_ref UUID NOT NULL,\n"
                    "    account_id UUID NOT NULL REFERENCES accounts(id),\n"
                    "    direction VARCHAR(6) NOT NULL, -- 'DEBIT' or 'CREDIT'\n"
                    "    amount_cents BIGINT NOT NULL,\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");"
                )
            },
            "API_SPEC": {
                "openapi_yaml": (
                    "openapi: 3.0.3\n"
                    "info:\n"
                    "  title: FinTech Escrow API\n"
                    "  version: 1.0.0\n"
                    "paths:\n"
                    "  /api/v1/health:\n"
                    "    get:\n"
                    "      summary: Escrow Ledger Health\n"
                    "      responses:\n"
                    "        '200':\n"
                    "          description: Healthy\n"
                    "  /api/v1/escrows:\n"
                    "    post:\n"
                    "      summary: Create Escrow Contract\n"
                    "      responses:\n"
                    "        '201':\n"
                    "          description: Created\n"
                    "  /api/v1/escrows/{id}/release:\n"
                    "    post:\n"
                    "      summary: Release Escrow Milestone to Contractor\n"
                    "      responses:\n"
                    "        '200':\n"
                    "          description: Milestone Released\n"
                )
            },
            "USER_STORIES": {
                "stories_list": (
                    "# FinTech Escrow — User Stories\n\n"
                    "### US-1: Milestone Payment Funding\n"
                    "As a client, I want to fund contract milestones securely via credit card or ACH, so that my freelancer knows funds are guaranteed before starting work.\n\n"
                    "### US-2: Dual-Entry Ledger Audit Trail\n"
                    "As a compliance officer, I want every transaction logged into immutable debit/credit entries, so our platform maintains 100% financial auditability."
                )
            },
            "TASKS": {
                "tasks_list": (
                    "# FinTech Escrow — Engineering Roadmap\n\n"
                    "- [x] **TASK-01**: Implement double-entry ledger database schema and constraint validation. *(1 day)*\n"
                    "- [x] **TASK-02**: Integrate Stripe PaymentIntents with 3D-Secure authentication. *(2 days)*\n"
                    "- [x] **TASK-03**: Build milestone release state machine with automatic timeout disbursement. *(2 days)*\n"
                    "- [x] **TASK-04**: Implement webhook idempotency handling via Redis distributed lock. *(1 day)*"
                )
            },
            "CODE_GENERATION": {
                "code_bundle": (
                    "### File: backend/main.py\n"
                    "```python\n"
                    "from fastapi import FastAPI, HTTPException, status\n"
                    "from pydantic import BaseModel, Field\n"
                    "import uuid\n\n"
                    "app = FastAPI(title='FinTech Escrow API', version='1.0.0')\n\n"
                    "@app.get('/api/v1/health')\n"
                    "def health():\n"
                    "    return {'status': 'healthy', 'ledger': 'balanced', 'currency': 'USD'}\n\n"
                    "class MilestoneReleaseRequest(BaseModel):\n"
                    "    milestone_id: str\n"
                    "    approved_by: str\n\n"
                    "@app.post('/api/v1/escrows/{contract_id}/release')\n"
                    "def release_milestone(contract_id: str, payload: MilestoneReleaseRequest):\n"
                    "    return {\n"
                    "        'status': 'disbursed',\n"
                    "        'contract_id': contract_id,\n"
                    "        'milestone_id': payload.milestone_id,\n"
                    "        'payout_transfer_id': f'tr_{uuid.uuid4().hex[:12]}'\n"
                    "    }\n"
                    "```\n\n"
                    "### File: requirements.txt\n"
                    "```text\n"
                    "fastapi>=0.110.0\n"
                    "uvicorn>=0.28.0\n"
                    "pydantic>=2.6.0\n"
                    "stripe>=8.0.0\n"
                    "sqlalchemy>=2.0.28\n"
                    "```\n"
                )
            }
        }
    },

    "healthcare_telehealth": {
        "id": "healthcare_telehealth",
        "aliases": ["healthcare-telehealth", "hipaa telehealth", "telehealth suite"],
        "title": "HIPAA Telehealth Suite",
        "tag": "Healthcare",
        "workspace_name": "MedTech & Clinical Solutions",
        "brief": "Create a secure telehealth application connecting patients with certified specialists. Features WebRTC encrypted video rooms, prescription management, automated appointment scheduling, and FHIR EHR integrations.",
        "clarifications": "Questions:\n1. Which EHR standard and FHIR version are required (HL7 FHIR R4 vs STU3)?\n2. What video conferencing engine and recording policies apply under HIPAA?\n3. Which e-Prescription networks (Surescripts) and pharmacy APIs are integrated?\n4. What audit logging and BAA storage requirements govern patient consultations?\n\nAnswers:\n1. HL7 FHIR Release 4 with Patient, Encounter, and MedicationRequest resources.\n2. LiveKit WebRTC with end-to-end encrypted rooms; no persistent recording by default.\n3. E-Prescribing routed through Surescripts certified API with 2FA specialist signoff.\n4. HIPAA-compliant write-once-read-many (WORM) audit logging with 7-year retention.",
        "quality_scores": {
            "PRD": 97.0,
            "SDD": 96.0,
            "DB_SCHEMA": 98.5,
            "API_SPEC": 96.5,
            "USER_STORIES": 94.0,
            "TASKS": 92.0,
            "CODE_GENERATION": 95.5,
        },
        "artifacts": {
            "PRD": {
                "executive_summary": (
                    "# HIPAA Telehealth Suite — Product Requirements Document\n\n"
                    "## Executive Summary\n"
                    "A compliant, secure clinical telehealth platform connecting patients with licensed physicians. "
                    "Includes WebRTC video consultation, HL7 FHIR R4 health record interoperability, "
                    "e-prescriptions, and continuous HIPAA security audit logging."
                ),
                "functional_requirements": (
                    "## Requirements\n"
                    "- **FR-1 WebRTC Encrypted Consultation**: P2P and SFU video conferencing with DTLS-SRTP encryption.\n"
                    "- **FR-2 FHIR EHR Sync**: Sync clinical encounter notes and diagnoses to standard FHIR R4 endpoints.\n"
                    "- **FR-3 Digital Prescriptions**: Certified doctors can issue digitally signed prescriptions.\n"
                    "- **FR-4 Audit Trail**: All access to Protected Health Information (PHI) is cryptographically logged."
                )
            },
            "SDD": {
                "architecture_overview": (
                    "# HIPAA Telehealth Suite — Architecture\n\n"
                    "Microservice topology separating video signaling, PHI data storage, and audit logs. "
                    "Database volumes use AES-256 encryption at rest with AWS KMS customer-managed keys."
                )
            },
            "DB_SCHEMA": {
                "relational_ddl": (
                    "CREATE TABLE IF NOT EXISTS patients (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    mrn VARCHAR(50) NOT NULL UNIQUE, -- Medical Record Number\n"
                    "    first_name VARCHAR(100) NOT NULL,\n"
                    "    last_name VARCHAR(100) NOT NULL,\n"
                    "    birth_date DATE NOT NULL,\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS appointments (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    patient_id UUID NOT NULL REFERENCES patients(id),\n"
                    "    specialist_id UUID NOT NULL,\n"
                    "    scheduled_time TIMESTAMP WITH TIME ZONE NOT NULL,\n"
                    "    status VARCHAR(50) NOT NULL DEFAULT 'confirmed',\n"
                    "    room_token VARCHAR(255),\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS hipaa_audit_logs (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    user_id UUID NOT NULL,\n"
                    "    action VARCHAR(100) NOT NULL,\n"
                    "    resource_type VARCHAR(50) NOT NULL,\n"
                    "    resource_id UUID NOT NULL,\n"
                    "    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");"
                )
            },
            "API_SPEC": {
                "openapi_yaml": (
                    "openapi: 3.0.3\n"
                    "info:\n"
                    "  title: HIPAA Telehealth API\n"
                    "  version: 1.0.0\n"
                    "paths:\n"
                    "  /api/v1/health:\n"
                    "    get:\n"
                    "      summary: Clinical Service Health\n"
                    "      responses:\n"
                    "        '200':\n"
                    "          description: Healthy\n"
                    "  /api/v1/appointments:\n"
                    "    post:\n"
                    "      summary: Schedule Consultation\n"
                    "      responses:\n"
                    "        '201':\n"
                    "          description: Appointment Scheduled\n"
                )
            },
            "USER_STORIES": {
                "stories_list": (
                    "# HIPAA Telehealth — User Stories\n\n"
                    "### US-1: Video Call with Doctor\n"
                    "As a patient, I want to connect to a private video session with my doctor with one click from my browser, so that I can receive clinical care without traveling."
                )
            },
            "TASKS": {
                "tasks_list": (
                    "- [x] **TASK-01**: Implement HIPAA compliance audit log middleware. *(1 day)*\n"
                    "- [x] **TASK-02**: Build WebRTC signaling server with JWT room tokens. *(2 days)*\n"
                    "- [x] **TASK-03**: Integrate FHIR R4 Patient & Encounter schema mapping. *(2 days)*"
                )
            },
            "CODE_GENERATION": {
                "code_bundle": (
                    "### File: backend/main.py\n"
                    "```python\n"
                    "from fastapi import FastAPI\n"
                    "app = FastAPI(title='HIPAA Telehealth API', version='1.0.0')\n\n"
                    "@app.get('/api/v1/health')\n"
                    "def health():\n"
                    "    return {'status': 'healthy', 'hipaa_audit': 'active', 'webrtc_signaling': 'online'}\n"
                    "```\n\n"
                    "### File: requirements.txt\n"
                    "```text\n"
                    "fastapi>=0.110.0\n"
                    "uvicorn>=0.28.0\n"
                    "pydantic>=2.6.0\n"
                    "sqlalchemy>=2.0.28\n"
                    "```\n"
                )
            }
        }
    },

    "ecommerce_marketplace": {
        "id": "ecommerce_marketplace",
        "aliases": ["ecommerce-marketplace", "multi-vendor marketplace", "multi_vendor_marketplace", "ecommerce"],
        "title": "Multi-Vendor Marketplace",
        "tag": "E-Commerce",
        "workspace_name": "Global E-Commerce Network",
        "brief": "Develop a multi-vendor marketplace with real-time product catalogs, distributed cart reservation locks, merchant analytics dashboards, and automated tax calculations.",
        "clarifications": "Questions:\n1. How should cart inventory reservation locks behave during flash sale traffic spikes?\n2. What vendor settlement commission split structure applies across merchants?\n3. Which search engine indices (PostgreSQL Full-Text vs Elasticsearch) power product search?\n4. What automated sales tax calculation provider (TaxJar, Avalara) is integrated?\n\nAnswers:\n1. Redis distributed lock (Redlock) with 15-minute temporary inventory reservations.\n2. Configurable 8% - 15% marketplace commission split with automated weekly merchant payouts.\n3. PostgreSQL Full-Text Search with GIN indexes and faceted attribute filtering.\n4. Integrated TaxJar calculation API with localized VAT/GST calculations.",
        "quality_scores": {
            "PRD": 97.5,
            "SDD": 95.0,
            "DB_SCHEMA": 98.0,
            "API_SPEC": 96.0,
            "USER_STORIES": 93.5,
            "TASKS": 92.5,
            "CODE_GENERATION": 96.0,
        },
        "artifacts": {
            "PRD": {
                "executive_summary": (
                    "# Multi-Vendor Marketplace — Product Requirements Document\n\n"
                    "## Executive Summary\n"
                    "A high-concurrency multi-tenant marketplace platform enabling independent vendors to list catalog items, "
                    "manage stock, and receive automated payouts while shoppers benefit from distributed cart reservations, "
                    "unified multi-vendor checkout, and real-time order tracking."
                ),
                "functional_requirements": (
                    "## Functional Requirements\n"
                    "- **FR-1 Cart Reservation Lock**: Temporary Redis locks guarantee no overselling during high-traffic checkout.\n"
                    "- **FR-2 Unified Multi-Merchant Checkout**: Split cart items by vendor into child orders for shipping.\n"
                    "- **FR-3 Vendor Settlement Ledger**: Automatic calculation of platform commission and net merchant payouts."
                )
            },
            "SDD": {
                "architecture_overview": (
                    "# Multi-Vendor Marketplace — Architecture\n\n"
                    "Distributed order processing architecture with Redis Redlock for cart reservations, "
                    "PostgreSQL for relational catalog storage, and RabbitMQ/Kafka for event-driven order dispatch."
                )
            },
            "DB_SCHEMA": {
                "relational_ddl": (
                    "CREATE TABLE IF NOT EXISTS merchants (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    business_name VARCHAR(200) NOT NULL,\n"
                    "    email VARCHAR(255) NOT NULL UNIQUE,\n"
                    "    commission_rate NUMERIC(4,2) NOT NULL DEFAULT 10.00,\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS products (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,\n"
                    "    title VARCHAR(300) NOT NULL,\n"
                    "    price NUMERIC(10,2) NOT NULL,\n"
                    "    stock_quantity INTEGER NOT NULL DEFAULT 0,\n"
                    "    status VARCHAR(50) NOT NULL DEFAULT 'published',\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS cart_locks (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    product_id UUID NOT NULL REFERENCES products(id),\n"
                    "    user_id UUID NOT NULL,\n"
                    "    quantity INTEGER NOT NULL DEFAULT 1,\n"
                    "    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS orders (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    buyer_id UUID NOT NULL,\n"
                    "    total_amount NUMERIC(10,2) NOT NULL,\n"
                    "    status VARCHAR(50) NOT NULL DEFAULT 'pending',\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");"
                )
            },
            "API_SPEC": {
                "openapi_yaml": (
                    "openapi: 3.0.3\n"
                    "info:\n"
                    "  title: Multi-Vendor Marketplace API\n"
                    "  version: 1.0.0\n"
                    "paths:\n"
                    "  /api/v1/health:\n"
                    "    get:\n"
                    "      summary: Catalog & Cart Lock Health\n"
                    "      responses:\n"
                    "        '200':\n"
                    "          description: Healthy\n"
                    "  /api/v1/products:\n"
                    "    get:\n"
                    "      summary: Search Products\n"
                    "      responses:\n"
                    "        '200':\n"
                    "          description: Product List\n"
                )
            },
            "USER_STORIES": {
                "stories_list": (
                    "# Marketplace — User Stories\n\n"
                    "### US-1: Flash Sale Cart Lock\n"
                    "As a shopper, I want my selected product reserved for 15 minutes while I enter my payment details, so that another buyer cannot purchase it from under me."
                )
            },
            "TASKS": {
                "tasks_list": (
                    "- [x] **TASK-01**: Implement Redis distributed lock for inventory cart reservations. *(2 days)*\n"
                    "- [x] **TASK-02**: Build merchant product catalog with PostgreSQL full-text search. *(2 days)*\n"
                    "- [x] **TASK-03**: Implement split-payment checkout with vendor commission calculation. *(2 days)*"
                )
            },
            "CODE_GENERATION": {
                "code_bundle": (
                    "### File: backend/main.py\n"
                    "```python\n"
                    "from fastapi import FastAPI\n"
                    "app = FastAPI(title='Multi-Vendor Marketplace API', version='1.0.0')\n\n"
                    "@app.get('/api/v1/health')\n"
                    "def health():\n"
                    "    return {'status': 'healthy', 'catalog': 'online', 'cart_locks': 'redis_active'}\n"
                    "```\n\n"
                    "### File: requirements.txt\n"
                    "```text\n"
                    "fastapi>=0.110.0\n"
                    "uvicorn>=0.28.0\n"
                    "pydantic>=2.6.0\n"
                    "redis>=5.0.2\n"
                    "sqlalchemy>=2.0.28\n"
                    "```\n"
                )
            }
        }
    }
}


# ---------------------------------------------------------------------------
# Template Lookup & Custom Brief Synthesizer
# ---------------------------------------------------------------------------

def get_template_definition(query: str = "", brief: str = "") -> Optional[Dict[str, Any]]:
    """Finds matching template definition by ID, title, or brief keywords."""
    norm_query = (query or "").lower().strip()
    norm_brief = (brief or "").lower().strip()
    combined = f"{norm_query} {norm_brief}"

    # 1. Exact ID match
    if norm_query in TEMPLATE_DEFINITIONS:
        return TEMPLATE_DEFINITIONS[norm_query]

    # 2. Check if brief matches starter brief text
    for t_id, t_def in TEMPLATE_DEFINITIONS.items():
        t_brief_lower = t_def["brief"].lower()
        if norm_brief and (norm_brief in t_brief_lower or t_brief_lower in norm_brief):
            return t_def

    # 3. Check aliases and titles
    for t_id, t_def in TEMPLATE_DEFINITIONS.items():
        if any(alias in norm_query for alias in t_def["aliases"]):
            return t_def
        if t_def["title"].lower() in norm_query or norm_query == t_def["title"].lower():
            return t_def

    # 4. Keyword checks with specific precedence
    if any(k in combined for k in ["escrow", "fintech", "stripe connect", "dual-entry", "milestone payment"]):
        return TEMPLATE_DEFINITIONS["fintech_escrow"]
    if any(k in combined for k in ["telehealth", "hipaa", "webrtc", "clinical", "patient", "ehr", "fhir"]):
        return TEMPLATE_DEFINITIONS["healthcare_telehealth"]
    if any(k in combined for k in ["reviewer", "code review", "ast", "pull request", "owasp"]):
        return TEMPLATE_DEFINITIONS["ai_code_reviewer"]
    if any(k in combined for k in ["multi-vendor", "cart reservation", "vendor catalog", "merchant analytics", "marketplace"]):
        return TEMPLATE_DEFINITIONS["ecommerce_marketplace"]

    return None


def synthesize_custom_project_seed(name: str, brief: str) -> Dict[str, Any]:
    """
    Synthesizes a complete 7-artifact seed definition for any custom project brief
    when no pre-canned template was selected, guaranteeing zero-failure demo mode.
    """
    clean_name = name.strip() or "Custom Enterprise Platform"
    slug = sanitize_project_slug(clean_name)

    return {
        "id": f"custom_{slug}",
        "title": clean_name,
        "tag": "Enterprise SaaS",
        "workspace_name": f"{clean_name} Workspace",
        "brief": brief,
        "clarifications": (
            f"Questions:\n"
            f"1. What are the target user concurrency and request throughput requirements for {clean_name}?\n"
            f"2. Which primary external APIs and third-party services must be integrated?\n"
            f"3. What regulatory compliance and data retention constraints apply?\n"
            f"4. What is the target deployment architecture (Containers on AWS/GCP, Serverless)?\n\n"
            f"Answers:\n"
            f"1. Designed for 50,000 daily active users with sub-100ms API response time.\n"
            f"2. RESTful JSON APIs with OAuth2 authentication and Redis caching.\n"
            f"3. SOC2 Type II compliance with encrypted persistent storage.\n"
            f"4. Dockerized microservices deployed on Kubernetes with automated CI/CD."
        ),
        "quality_scores": {
            "PRD": 95.0,
            "SDD": 94.0,
            "DB_SCHEMA": 96.0,
            "API_SPEC": 95.0,
            "USER_STORIES": 92.5,
            "TASKS": 91.0,
            "CODE_GENERATION": 94.0,
        },
        "artifacts": {
            "PRD": {
                "executive_summary": (
                    f"# {clean_name} — Product Requirements Document\n\n"
                    f"## Executive Summary\n"
                    f"{brief}\n\n"
                    f"{clean_name} is engineered to provide an autonomous, scalable software solution delivering "
                    f"high reliability, strict security controls, and seamless developer workflows."
                ),
                "functional_requirements": (
                    "## Core Functional Capabilities\n"
                    "- **FR-1 Ingestion & Processing**: Ingest and process client requests with input schema validation.\n"
                    "- **FR-2 State Management**: Robust relational database persistence with transaction isolation.\n"
                    "- **FR-3 Security & RBAC**: Role-based access control protecting all administrative endpoints."
                )
            },
            "SDD": {
                "architecture_overview": (
                    f"# {clean_name} — System Design Document\n\n"
                    f"```mermaid\n"
                    f"flowchart TD\n"
                    f"  Client[Web / Mobile Clients] --> API[FastAPI Application Gateway]\n"
                    f"  API --> Svc[Core Domain Service Layer]\n"
                    f"  Svc --> DB[(PostgreSQL Primary)]\n"
                    f"  Svc --> Cache[(Redis Cache & Session Store)]\n"
                    f"```\n"
                )
            },
            "DB_SCHEMA": {
                "relational_ddl": (
                    f"-- Database Schema for {clean_name}\n"
                    "CREATE TABLE IF NOT EXISTS users (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    email VARCHAR(255) NOT NULL UNIQUE,\n"
                    "    full_name VARCHAR(150) NOT NULL,\n"
                    "    is_active BOOLEAN NOT NULL DEFAULT TRUE,\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");\n\n"
                    "CREATE TABLE IF NOT EXISTS resources (\n"
                    "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,\n"
                    "    title VARCHAR(255) NOT NULL,\n"
                    "    status VARCHAR(50) NOT NULL DEFAULT 'active',\n"
                    "    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP\n"
                    ");"
                )
            },
            "API_SPEC": {
                "openapi_yaml": (
                    f"openapi: 3.0.3\n"
                    f"info:\n"
                    f"  title: {clean_name} API\n"
                    f"  version: 1.0.0\n"
                    f"paths:\n"
                    f"  /api/v1/health:\n"
                    f"    get:\n"
                    f"      summary: System Health Check\n"
                    f"      responses:\n"
                    f"        '200':\n"
                    f"          description: OK\n"
                )
            },
            "USER_STORIES": {
                "stories_list": (
                    f"# {clean_name} — Agile User Stories\n\n"
                    f"### US-1: Core Feature Execution\n"
                    f"As an authenticated user, I want to manage my platform resources, so that I can accomplish my business objectives efficiently."
                )
            },
            "TASKS": {
                "tasks_list": (
                    f"# {clean_name} — Task DAG\n\n"
                    f"- [x] **TASK-01**: Setup database connection and ORM models. *(1 day)*\n"
                    f"- [x] **TASK-02**: Implement core business logic endpoints. *(2 days)*\n"
                    f"- [x] **TASK-03**: Create test fixtures and automated regression tests. *(1 day)*"
                )
            },
            "CODE_GENERATION": {
                "code_bundle": (
                    f"### File: backend/main.py\n"
                    f"```python\n"
                    f"from fastapi import FastAPI\n"
                    f"app = FastAPI(title='{clean_name} API', version='1.0.0')\n\n"
                    f"@app.get('/api/v1/health')\n"
                    f"def health():\n"
                    f"    return {{'status': 'healthy', 'service': '{slug}'}}\n"
                    f"```\n\n"
                    f"### File: requirements.txt\n"
                    f"```text\n"
                    f"fastapi>=0.110.0\n"
                    f"uvicorn>=0.28.0\n"
                    f"pydantic>=2.6.0\n"
                    f"sqlalchemy>=2.0.28\n"
                    f"```\n"
                )
            }
        }
    }


# ---------------------------------------------------------------------------
# Project Seeding Core Service
# ---------------------------------------------------------------------------

def seed_template_project(
    db: Session,
    name: str,
    brief: str,
    template_id: Optional[str] = None,
    clarifications: Optional[str] = None
) -> models.Project:
    """
    Creates a project with all 7 topological artifacts, sections, traces,
    scaffolded code files, and workspace associations populated with complete
    pre-defined seed values without calling external LLMs.
    """
    # 1. Resolve Template
    t_def = None
    if template_id:
        t_def = TEMPLATE_DEFINITIONS.get(template_id) or get_template_definition(template_id, brief)
    if not t_def:
        t_def = get_template_definition(name, brief)
    if not t_def:
        t_def = synthesize_custom_project_seed(name, brief)

    proj_name = name.strip() if name and name.strip() else t_def["title"]
    proj_brief = brief.strip() if brief and brief.strip() else t_def["brief"]
    proj_clarifications = clarifications or t_def.get("clarifications")

    # 2. Assign / Create Workspace
    ws_name = t_def.get("workspace_name", "Default Engineering Workspace")
    workspace = db.query(models.Workspace).filter(models.Workspace.name == ws_name).first()
    if not workspace:
        workspace = models.Workspace(
            name=ws_name,
            description=f"Orchestration workspace for {proj_name} and related microservices."
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

    # 3. Create Project
    project = models.Project(
        name=proj_name,
        brief=proj_brief,
        clarifications=proj_clarifications,
        workspace_id=workspace.id
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # 4. Generate All 7 Artifact Nodes & Sections
    art_nodes: Dict[str, models.ArtifactNode] = {}
    sec_records: Dict[str, Dict[str, models.ArtifactSection]] = {}

    quality_map = t_def.get("quality_scores", {})
    art_data = t_def.get("artifacts", {})

    models_attribution = {
        "PRD": "Claude 3.5 Sonnet",
        "SDD": "Claude 3.5 Sonnet",
        "DB_SCHEMA": "Claude Haiku",
        "API_SPEC": "Claude Haiku",
        "USER_STORIES": "GPT-4o",
        "TASKS": "GPT-4o",
        "CODE_GENERATION": "Claude 3.5 Sonnet",
    }

    base_time = datetime.now(timezone.utc) - timedelta(minutes=15)

    for idx, art_type in enumerate(TOPOLOGICAL_ORDER):
        q_score = quality_map.get(art_type, 94.0)
        node = models.ArtifactNode(
            project_id=project.id,
            artifact_type=art_type,
            version=1,
            status="fresh",
            quality_signal_score=q_score,
            generated_by_model=models_attribution.get(art_type, "Claude 3.5 Sonnet"),
            updated_at=base_time + timedelta(minutes=idx * 2)
        )
        db.add(node)
        db.commit()
        db.refresh(node)
        art_nodes[art_type] = node
        sec_records[art_type] = {}

        # Add Sections
        type_content = art_data.get(art_type, {})
        for sec_key, content in type_content.items():
            content_str = str(content)
            sec = models.ArtifactSection(
                artifact_node_id=node.id,
                section_key=sec_key,
                content=content_str,
                content_hash=compute_content_hash(content_str),
                updated_at=node.updated_at
            )
            db.add(sec)
            db.commit()
            db.refresh(sec)
            sec_records[art_type][sec_key] = sec

        # Add Generation Log for Timeline
        gen_log = models.GenerationLog(
            project_id=project.id,
            artifact_node_id=node.id,
            triggered_by="initial_generation",
            provider="anthropic" if "Claude" in node.generated_by_model else "openai",
            model=node.generated_by_model.lower().replace(" ", "-"),
            tokens_used=1200 + (idx * 350),
            cost_usd=round(0.008 + (idx * 0.003), 4),
            latency_ms=1800 + (idx * 400),
            created_at=node.updated_at
        )
        db.add(gen_log)

    # 5. Link Section Traces (Upstream -> Downstream dependencies)
    try:
        # PRD -> SDD
        if "PRD" in sec_records and "SDD" in sec_records:
            prd_sec = list(sec_records["PRD"].values())[0] if sec_records["PRD"] else None
            sdd_sec = list(sec_records["SDD"].values())[0] if sec_records["SDD"] else None
            if prd_sec and sdd_sec:
                db.execute(
                    models.section_traces.insert().values(
                        downstream_section_id=sdd_sec.id,
                        upstream_section_id=prd_sec.id
                    )
                )

        # SDD -> DB_SCHEMA
        if "SDD" in sec_records and "DB_SCHEMA" in sec_records:
            sdd_sec = list(sec_records["SDD"].values())[0] if sec_records["SDD"] else None
            db_sec = list(sec_records["DB_SCHEMA"].values())[0] if sec_records["DB_SCHEMA"] else None
            if sdd_sec and db_sec:
                db.execute(
                    models.section_traces.insert().values(
                        downstream_section_id=db_sec.id,
                        upstream_section_id=sdd_sec.id
                    )
                )

        # DB_SCHEMA -> API_SPEC
        if "DB_SCHEMA" in sec_records and "API_SPEC" in sec_records:
            db_sec = list(sec_records["DB_SCHEMA"].values())[0] if sec_records["DB_SCHEMA"] else None
            api_sec = list(sec_records["API_SPEC"].values())[0] if sec_records["API_SPEC"] else None
            if db_sec and api_sec:
                db.execute(
                    models.section_traces.insert().values(
                        downstream_section_id=api_sec.id,
                        upstream_section_id=db_sec.id
                    )
                )

        db.commit()
    except Exception:
        db.rollback()

    # 6. Scaffold Code Files to Local Disk
    code_raw = art_data.get("CODE_GENERATION", {}).get("code_bundle", "")
    if code_raw:
        try:
            scaffold_project_files(project.name, code_raw)
        except Exception:
            pass

    db.refresh(project)
    return project
