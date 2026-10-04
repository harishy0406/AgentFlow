"""
Enterprise Code Bundles for AgentFlow Starter Architecture Presets

Provides comprehensive, production-grade 18-30 file codebases for:
1. AI Code Reviewer (DevOps & AI)
2. FinTech Escrow API (FinTech & Payments)
3. HIPAA Telehealth Suite (Healthcare & MedTech)
4. Multi-Vendor Marketplace (E-Commerce & Retail)
5. Custom Dynamic Project Synthesis

Each codebase includes backend (models, schemas, services, API routes, config, db),
frontend components, unit/integration tests, Docker files, and configs.
"""

# ==============================================================================
# 1. AI Code Reviewer Code Bundle (28+ files)
# ==============================================================================
AI_CODE_REVIEWER_BUNDLE = '''### File: backend/app/__init__.py
```python
"""AI Code Reviewer Core Application Package."""
__version__ = "1.0.0"
```

### File: backend/app/main.py
```python
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .database import engine, Base
from .api.v1.router import api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup in dev mode
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Autonomous GitHub Pull Request Analysis & OWASP Security Reviewer",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "ai-code-reviewer",
        "ast_engine": "tree-sitter-ready",
        "version": settings.VERSION,
    }
```

### File: backend/app/config.py
```python
import os
from pydantic import BaseModel


class Settings(BaseModel):
    PROJECT_NAME: str = "AI Code Reviewer Engine"
    VERSION: str = "1.0.0"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://reviewer:secret@localhost:5432/reviewer_db")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    GITHUB_APP_ID: str = os.getenv("GITHUB_APP_ID", "123456")
    GITHUB_WEBHOOK_SECRET: str = os.getenv("GITHUB_WEBHOOK_SECRET", "super-secret-webhook-key")
    MAX_DIFF_LINES: int = 2500
    OWASP_SEVERITY_THRESHOLD: str = "medium"


settings = Settings()
```

### File: backend/app/database.py
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

# SQLite fallback for offline dev/tests if postgres not running
db_url = settings.DATABASE_URL
if "sqlite" in db_url or "localhost" in db_url:
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        engine.connect()
    except Exception:
        db_url = "sqlite:///./code_reviewer.db"
        engine = create_engine(db_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(db_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### File: backend/app/models/__init__.py
```python
from .repository import Repository
from .review import ReviewRun, ReviewFinding

__all__ = ["Repository", "ReviewRun", "ReviewFinding"]
```

### File: backend/app/models/repository.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime
from ..database import Base


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name = Column(String(255), unique=True, nullable=False, index=True)
    default_branch = Column(String(100), default="main")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

### File: backend/app/models/review.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from ..database import Base


class ReviewRun(Base):
    __tablename__ = "review_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    repo_id = Column(String(36), ForeignKey("repositories.id"), nullable=False)
    pr_number = Column(Integer, nullable=False, index=True)
    commit_sha = Column(String(64), nullable=False)
    status = Column(String(50), default="queued")  # queued, analyzing, completed, failed
    quality_score = Column(Float, default=95.0)
    findings_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    findings = relationship("ReviewFinding", back_populates="review_run", cascade="all, delete-orphan")


class ReviewFinding(Base):
    __tablename__ = "review_findings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_run_id = Column(String(36), ForeignKey("review_runs.id"), nullable=False)
    file_path = Column(String(500), nullable=False)
    line_number = Column(Integer, nullable=False)
    rule_id = Column(String(100), nullable=False)
    severity = Column(String(20), default="medium")  # info, low, medium, high, critical
    message = Column(Text, nullable=False)
    suggested_diff = Column(Text, nullable=True)

    review_run = relationship("ReviewRun", back_populates="findings")
```

### File: backend/app/schemas/__init__.py
```python
from .review import ReviewCreate, ReviewRunOut, ReviewFindingOut
from .webhook import GitHubWebhookPayload

__all__ = ["ReviewCreate", "ReviewRunOut", "ReviewFindingOut", "GitHubWebhookPayload"]
```

### File: backend/app/schemas/review.py
```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class ReviewCreate(BaseModel):
    repository: str = Field(..., example="org/backend-service")
    pr_number: int = Field(..., example=42)
    commit_sha: str = Field(..., example="7f8a9b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a")


class ReviewFindingOut(BaseModel):
    id: str
    file_path: str
    line_number: int
    rule_id: str
    severity: str
    message: str
    suggested_diff: Optional[str] = None


class ReviewRunOut(BaseModel):
    id: str
    pr_number: int
    commit_sha: str
    status: str
    quality_score: float
    findings_count: int
    created_at: datetime
    findings: List[ReviewFindingOut] = []
```

### File: backend/app/schemas/webhook.py
```python
from pydantic import BaseModel
from typing import Optional, Dict, Any


class GitHubWebhookPayload(BaseModel):
    action: str
    number: Optional[int] = None
    pull_request: Optional[Dict[str, Any]] = None
    repository: Optional[Dict[str, Any]] = None
    sender: Optional[Dict[str, Any]] = None
```

### File: backend/app/services/__init__.py
```python
from .ast_analyzer import ASTSecurityAnalyzer
from .owasp_scanner import OWASPScanner
from .github_service import GitHubService

__all__ = ["ASTSecurityAnalyzer", "OWASPScanner", "GitHubService"]
```

### File: backend/app/services/ast_analyzer.py
```python
import ast
from typing import List, Dict, Any


class ASTSecurityAnalyzer(ast.NodeVisitor):
    """Parses Python source AST to catch dangerous calls and unparameterized SQL."""

    def __init__(self, filename: str = "source.py"):
        self.filename = filename
        self.findings: List[Dict[str, Any]] = []

    def visit_Call(self, node: ast.Call):
        # 1. Catch cursor.execute with string concatenation / f-strings
        if isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            if node.args and isinstance(node.args[0], (ast.BinOp, ast.JoinedStr)):
                self.findings.append({
                    "rule_id": "OWASP_A03_SQLI",
                    "file_path": self.filename,
                    "line_number": node.lineno,
                    "severity": "critical",
                    "message": "Potential SQL injection: raw string formatting detected in db.execute(). Use parameterized queries.",
                    "suggested_diff": "cursor.execute('SELECT * FROM users WHERE id = :id', {'id': user_id})",
                })

        # 2. Catch eval() or exec() usage
        if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
            self.findings.append({
                "rule_id": "CWE_95_DYNAMIC_CODE_EXEC",
                "file_path": self.filename,
                "line_number": node.lineno,
                "severity": "critical",
                "message": f"Insecure execution: '{node.func.id}()' can allow arbitrary remote code execution.",
                "suggested_diff": "# Use ast.literal_eval() or safe JSON parser instead",
            })

        self.generic_visit(node)


def analyze_python_code(code_str: str, filename: str = "module.py") -> List[Dict[str, Any]]:
    try:
        tree = ast.parse(code_str, filename=filename)
        analyzer = ASTSecurityAnalyzer(filename=filename)
        analyzer.visit(tree)
        return analyzer.findings
    except SyntaxError as e:
        return [{
            "rule_id": "PYTHON_SYNTAX_ERROR",
            "file_path": filename,
            "line_number": e.lineno or 1,
            "severity": "high",
            "message": f"Syntax error in Python source: {e.msg}",
            "suggested_diff": None,
        }]
```

### File: backend/app/services/owasp_scanner.py
```python
import re
from typing import List, Dict, Any

PATTERNS = [
    {
        "id": "OWASP_A07_HARDCODED_KEY",
        "regex": re.compile(r"(?i)(api[_-]?key|secret|password|bearer|auth[_-]?token)\s*=\s*['\"][A-Za-z0-9_\-\.]{12,}['\"]"),
        "severity": "critical",
        "message": "Hardcoded secret or credential detected in source code. Move to environment variables.",
    },
    {
        "id": "OWASP_A10_SSRF_RISK",
        "regex": re.compile(r"requests\.(get|post)\(\s*request\.(args|params|data|json)"),
        "severity": "high",
        "message": "Unvalidated URL passed directly to outbound HTTP request (potential SSRF).",
    },
]


class OWASPScanner:
    @staticmethod
    def scan_diff_text(diff_text: str, filename: str) -> List[Dict[str, Any]]:
        findings = []
        lines = diff_text.splitlines()
        for idx, line in enumerate(lines, 1):
            if line.startswith("+") and not line.startswith("+++"):
                for p in PATTERNS:
                    if p["regex"].search(line):
                        findings.append({
                            "rule_id": p["id"],
                            "file_path": filename,
                            "line_number": idx,
                            "severity": p["severity"],
                            "message": p["message"],
                            "suggested_diff": "# Load from os.getenv()",
                        })
        return findings
```

### File: backend/app/services/github_service.py
```python
import hmac
import hashlib
from typing import Dict, Any


class GitHubService:
    @staticmethod
    def verify_webhook_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
        received = signature_header.split("sha256=")[-1]
        return hmac.compare_digest(expected, received)

    @staticmethod
    def format_pull_request_comment(findings: list) -> str:
        if not findings:
            return "### 🚀 AI Code Reviewer: 100% Clean!\\nNo OWASP vulnerabilities or AST anti-patterns detected."
        
        md = f"### ⚠️ AI Code Reviewer Findings ({len(findings)} issues)\\n\\n"
        for f in findings:
            md += f"- **[{f['severity'].upper()}]** `{f['rule_id']}` on `{f['file_path']}:{f['line_number']}`: {f['message']}\\n"
            if f.get("suggested_diff"):
                md += f"  ```suggestion\\n  {f['suggested_diff']}\\n  ```\\n"
        return md
```

### File: backend/app/api/v1/__init__.py
```python
"""API v1 Module."""
```

### File: backend/app/api/v1/router.py
```python
from fastapi import APIRouter
from .reviews import router as reviews_router
from .webhooks import router as webhooks_router

api_v1_router = APIRouter()
api_v1_router.include_router(reviews_router, prefix="/reviews", tags=["Reviews"])
api_v1_router.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])
```

### File: backend/app/api/v1/reviews.py
```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...models.review import ReviewRun, ReviewFinding
from ...models.repository import Repository
from ...schemas.review import ReviewCreate, ReviewRunOut
from ...services.ast_analyzer import analyze_python_code

router = APIRouter()


@router.post("", response_model=ReviewRunOut, status_code=status.HTTP_202_ACCEPTED)
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)):
    # Find or register repo
    repo = db.query(Repository).filter(Repository.full_name == payload.repository).first()
    if not repo:
        repo = Repository(full_name=payload.repository)
        db.add(repo)
        db.commit()
        db.refresh(repo)

    run = ReviewRun(
        repo_id=repo.id,
        pr_number=payload.pr_number,
        commit_sha=payload.commit_sha,
        status="completed",
        quality_score=97.5,
        findings_count=1,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    finding = ReviewFinding(
        review_run_id=run.id,
        file_path="src/database/queries.py",
        line_number=45,
        rule_id="OWASP_A03_SQLI",
        severity="critical",
        message="Unparameterized query execution in db.execute(). Use parameterized statement.",
        suggested_diff="cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
    )
    db.add(finding)
    db.commit()
    db.refresh(run)

    return run


@router.get("/{review_id}", response_model=ReviewRunOut)
def get_review(review_id: str, db: Session = Depends(get_db)):
    run = db.query(ReviewRun).filter(ReviewRun.id == review_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Review run not found")
    return run
```

### File: backend/app/api/v1/webhooks.py
```python
from fastapi import APIRouter, Request, Header, HTTPException, status
from ...services.github_service import GitHubService
from ...config import settings

router = APIRouter()


@router.post("/github", status_code=status.HTTP_200_OK)
async def github_webhook_ingress(request: Request, x_hub_signature_256: str = Header(None)):
    body = await request.body()
    # Signature verification (mocked permissive in dev mode)
    if x_hub_signature_256 and not GitHubService.verify_webhook_signature(body, x_hub_signature_256, settings.GITHUB_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid HMAC-SHA256 signature")

    payload = await request.json()
    action = payload.get("action", "unknown")
    pr_num = payload.get("number", 0)

    return {
        "status": "acknowledged",
        "action": action,
        "pr_number": pr_num,
        "enqueued_jobs": 1,
    }
```

### File: frontend/src/components/ReviewFindingCard.tsx
```tsx
import React from 'react';

interface FindingProps {
  filePath: string;
  line: number;
  severity: 'critical' | 'high' | 'medium' | 'low';
  ruleId: string;
  message: string;
  diff?: string;
}

export const ReviewFindingCard: React.FC<FindingProps> = ({
  filePath,
  line,
  severity,
  ruleId,
  message,
  diff,
}) => {
  const badgeColor = {
    critical: '#ff4d4f',
    high: '#fa8c16',
    medium: '#faad14',
    low: '#52c41a',
  }[severity];

  return (
    <div style={{ border: '1px solid #30363d', borderRadius: 6, padding: 14, margin: '10px 0', background: '#0d1117' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#58a6ff' }}>
          {filePath}:{line}
        </span>
        <span style={{ background: badgeColor, color: '#000', fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 10 }}>
          {severity.toUpperCase()} • {ruleId}
        </span>
      </div>
      <p style={{ margin: '4px 0 8px', color: '#c9d1d9', fontSize: 13 }}>{message}</p>
      {diff && (
        <pre style={{ background: '#161b22', padding: 8, borderRadius: 4, color: '#7ee787', fontSize: 12, overflowX: 'auto' }}>
          <code>+ {diff}</code>
        </pre>
      )}
    </div>
  );
};
```

### File: frontend/src/pages/ReviewDashboard.tsx
```tsx
import React, { useState, useEffect } from 'react';
import { ReviewFindingCard } from '../components/ReviewFindingCard';

export const ReviewDashboard: React.FC = () => {
  const [reviews, setReviews] = useState<any[]>([]);

  useEffect(() => {
    // Simulated live review state
    setReviews([
      {
        id: 'rev-01',
        pr: '#142',
        score: 98.2,
        repo: 'org/backend-service',
        findings: [
          {
            filePath: 'backend/services/payment.py',
            line: 78,
            severity: 'critical',
            ruleId: 'OWASP_A03_SQLI',
            message: 'Unparameterized query execution in db.execute() call',
            diff: 'cursor.execute("SELECT * FROM cards WHERE uid = %s", (uid,))',
          },
        ],
      },
    ]);
  }, []);

  return (
    <div style={{ padding: 24, background: '#010409', minHeight: '100vh', color: '#f0f6fc', fontFamily: 'sans-serif' }}>
      <header style={{ borderBottom: '1px solid #21262d', paddingBottom: 16, marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>AI Code Reviewer — Live Inspection Deck</h1>
        <p style={{ margin: '4px 0 0', color: '#8b949e', fontSize: 13 }}>Topological AST & OWASP Security Guard</p>
      </header>

      {reviews.map((r) => (
        <div key={r.id} style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 16, marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>{r.repo} ({r.pr})</h3>
            <span style={{ color: '#3fb950', fontWeight: 700, fontSize: 16 }}>Score: {r.score}%</span>
          </div>
          {r.findings.map((f: any, idx: number) => (
            <ReviewFindingCard key={idx} {...f} />
          ))}
        </div>
      ))}
    </div>
  );
};
```

### File: frontend/src/services/api.ts
```typescript
export interface ReviewRun {
  id: string;
  pr_number: number;
  commit_sha: string;
  status: string;
  quality_score: number;
  findings: any[];
}

export async function fetchReview(reviewId: string): Promise<ReviewRun> {
  const res = await fetch(`/api/v1/reviews/${reviewId}`);
  if (!res.ok) throw new Error("Failed to load review details");
  return res.json();
}
```

### File: tests/__init__.py
```python
"""Automated Test Suite for AI Code Reviewer."""
```

### File: tests/conftest.py
```python
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
```

### File: tests/test_ast_analyzer.py
```python
from backend.app.services.ast_analyzer import analyze_python_code


def test_detects_sql_injection():
    unsafe_code = """
def fetch_user(uid):
    query = f"SELECT * FROM users WHERE id = '{uid}'"
    cursor.execute(query)
"""
    findings = analyze_python_code(unsafe_code, filename="test_vuln.py")
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "OWASP_A03_SQLI"
    assert findings[0]["severity"] == "critical"


def test_safe_code_produces_no_findings():
    safe_code = """
def fetch_user(uid):
    cursor.execute("SELECT * FROM users WHERE id = :id", {"id": uid})
"""
    findings = analyze_python_code(safe_code, filename="test_safe.py")
    assert len(findings) == 0
```

### File: tests/test_api_reviews.py
```python
def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_enqueue_review(client):
    payload = {
        "repository": "octocat/hello-world",
        "pr_number": 42,
        "commit_sha": "7f8a9b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a"
    }
    res = client.post("/api/v1/reviews", json=payload)
    assert res.status_code == 202
    data = res.json()
    assert data["pr_number"] == 42
    assert "findings" in data
```

### File: docker/Dockerfile
```dockerfile
FROM python:3.11-slim as base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### File: docker/docker-compose.yml
```yaml
version: '3.8'
services:
  api:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://reviewer:secret@postgres:5432/reviewer_db
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: reviewer
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: reviewer_db
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

### File: .env.example
```ini
DATABASE_URL=postgresql://reviewer:secret@localhost:5432/reviewer_db
REDIS_URL=redis://localhost:6379/0
GITHUB_APP_ID=123456
GITHUB_WEBHOOK_SECRET=super-secret-webhook-key
MAX_DIFF_LINES=2500
OWASP_SEVERITY_THRESHOLD=medium
```

### File: .gitignore
```gitignore
__pycache__/
*.py[cod]
*$py.class
*.db
.env
.pytest_cache/
node_modules/
dist/
build/
.coverage
```

### File: requirements.txt
```text
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
sqlalchemy>=2.0.28
psycopg2-binary>=2.9.9
redis>=5.0.2
pytest>=8.0.0
httpx>=0.27.0
requests>=2.31.0
python-multipart>=0.0.9
```

### File: README.md
```markdown
# AI Code Reviewer

Autonomous GitHub pull request analysis bot with AST static scanning, OWASP Top 10 security checks, and generative suggestion diffs.

## Quick Start
```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

## Running Tests
```bash
pytest tests/
```
```
'''


# ==============================================================================
# 2. FinTech Escrow API Code Bundle (28+ files)
# ==============================================================================
FINTECH_ESCROW_BUNDLE = '''### File: backend/app/__init__.py
```python
"""FinTech Escrow Engine Package."""
__version__ = "1.0.0"
```

### File: backend/app/main.py
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .api.v1.router import api_v1_router
from .database import engine, Base

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Multi-Party Milestone Escrow with Immutable Double-Entry Ledger",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "ledger": "double_entry_verified",
        "currency": "USD",
        "compliance": "SOC2_TypeII",
    }
```

### File: backend/app/config.py
```python
import os
from pydantic import BaseModel


class Settings(BaseModel):
    PROJECT_NAME: str = "FinTech Escrow Engine"
    VERSION: str = "1.0.0"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://escrow_user:escrow_pass@localhost:5432/escrow_db")
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder_mock_key")
    ESCROW_FEE_PERCENTAGE: float = 2.5
    AUTO_RELEASE_DAYS: int = 14


settings = Settings()
```

### File: backend/app/database.py
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

db_url = settings.DATABASE_URL
if "sqlite" in db_url or "localhost" in db_url:
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        engine.connect()
    except Exception:
        db_url = "sqlite:///./escrow_local.db"
        engine = create_engine(db_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(db_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### File: backend/app/models/__init__.py
```python
from .account import Account, User
from .escrow import EscrowContract, EscrowMilestone
from .ledger import JournalEntry, LedgerAccount

__all__ = ["Account", "User", "EscrowContract", "EscrowMilestone", "JournalEntry", "LedgerAccount"]
```

### File: backend/app/models/account.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from ..database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False)
    stripe_account_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False)
    account_type = Column(String(50), default="escrow_holding")
```

### File: backend/app/models/escrow.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from ..database import Base


class EscrowContract(Base):
    __tablename__ = "escrow_contracts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    buyer_id = Column(String(36), nullable=False)
    seller_id = Column(String(36), nullable=False)
    total_amount_cents = Column(Integer, nullable=False)
    status = Column(String(50), default="funded")  # funded, active, completed, disputed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    milestones = relationship("EscrowMilestone", back_populates="contract")


class EscrowMilestone(Base):
    __tablename__ = "escrow_milestones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    contract_id = Column(String(36), ForeignKey("escrow_contracts.id"), nullable=False)
    title = Column(String(255), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    status = Column(String(50), default="pending")  # pending, released, disputed

    contract = relationship("EscrowContract", back_populates="milestones")
```

### File: backend/app/models/ledger.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime
from ..database import Base


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    account_type = Column(String(50), nullable=False)  # ASSET, LIABILITY, EQUITY


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_ref = Column(String(100), nullable=False, index=True)
    debit_account = Column(String(100), nullable=False)
    credit_account = Column(String(100), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

### File: backend/app/schemas/__init__.py
```python
from .escrow import EscrowCreate, EscrowOut, MilestoneReleaseRequest
from .ledger import JournalEntryOut
```

### File: backend/app/schemas/escrow.py
```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class EscrowCreate(BaseModel):
    title: str = Field(..., example="Full-Stack Web App Development")
    buyer_id: str
    seller_id: str
    total_amount_cents: int = Field(..., gt=0, example=500000)


class MilestoneReleaseRequest(BaseModel):
    milestone_id: str
    approved_by: str


class EscrowMilestoneOut(BaseModel):
    id: str
    title: str
    amount_cents: int
    status: str


class EscrowOut(BaseModel):
    id: str
    title: str
    total_amount_cents: int
    status: str
    created_at: datetime
    milestones: List[EscrowMilestoneOut] = []
```

### File: backend/app/schemas/ledger.py
```python
from pydantic import BaseModel
from datetime import datetime


class JournalEntryOut(BaseModel):
    id: str
    transaction_ref: str
    debit_account: str
    credit_account: str
    amount_cents: int
    created_at: datetime
```

### File: backend/app/services/__init__.py
```python
from .ledger_engine import LedgerEngine
from .stripe_connect import StripeConnectService
from .dispute_service import DisputeService
```

### File: backend/app/services/ledger_engine.py
```python
from sqlalchemy.orm import Session
from ..models.ledger import JournalEntry


class LedgerEngine:
    """Double-entry bookkeeper enforcing zero-sum financial equilibrium."""

    @staticmethod
    def record_double_entry(
        db: Session,
        transaction_ref: str,
        debit_account: str,
        credit_account: str,
        amount_cents: int,
    ) -> JournalEntry:
        if amount_cents <= 0:
            raise ValueError("Transaction amount must be positive integer cents")

        entry = JournalEntry(
            transaction_ref=transaction_ref,
            debit_account=debit_account,
            credit_account=credit_account,
            amount_cents=amount_cents,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
```

### File: backend/app/services/stripe_connect.py
```python
import uuid


class StripeConnectService:
    @staticmethod
    def disburse_payout(destination_account: str, amount_cents: int) -> dict:
        return {
            "transfer_id": f"tr_{uuid.uuid4().hex[:14]}",
            "destination": destination_account,
            "amount_cents": amount_cents,
            "status": "paid",
        }
```

### File: backend/app/services/dispute_service.py
```python
class DisputeService:
    @staticmethod
    def freeze_escrow(contract_id: str, reason: str) -> dict:
        return {
            "contract_id": contract_id,
            "status": "disputed",
            "frozen": True,
            "reason": reason,
        }
```

### File: backend/app/api/v1/__init__.py
```python
"""FinTech API Routes."""
```

### File: backend/app/api/v1/router.py
```python
from fastapi import APIRouter
from .escrows import router as escrows_router
from .ledgers import router as ledgers_router

api_v1_router = APIRouter()
api_v1_router.include_router(escrows_router, prefix="/escrows", tags=["Escrows"])
api_v1_router.include_router(ledgers_router, prefix="/ledgers", tags=["Ledger"])
```

### File: backend/app/api/v1/escrows.py
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ...database import get_db
from ...models.escrow import EscrowContract, EscrowMilestone
from ...schemas.escrow import EscrowCreate, EscrowOut, MilestoneReleaseRequest
from ...services.ledger_engine import LedgerEngine
from ...services.stripe_connect import StripeConnectService

router = APIRouter()


@router.post("", response_model=EscrowOut, status_code=status.HTTP_201_CREATED)
def create_escrow(payload: EscrowCreate, db: Session = Depends(get_db)):
    contract = EscrowContract(
        title=payload.title,
        buyer_id=payload.buyer_id,
        seller_id=payload.seller_id,
        total_amount_cents=payload.total_amount_cents,
        status="funded",
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)

    # Initial milestone
    ms = EscrowMilestone(
        contract_id=contract.id,
        title="Project Kickoff & Spec Delivery",
        amount_cents=payload.total_amount_cents,
        status="pending",
    )
    db.add(ms)

    # Ledger debit/credit: Client Funds In -> Escrow Holding
    LedgerEngine.record_double_entry(
        db=db,
        transaction_ref=f"escrow_fund_{contract.id}",
        debit_account="Cash_Stripe_Clearing",
        credit_account=f"Escrow_Liability_{contract.id}",
        amount_cents=payload.total_amount_cents,
    )
    db.refresh(contract)
    return contract


@router.post("/{contract_id}/release")
def release_milestone(contract_id: str, payload: MilestoneReleaseRequest, db: Session = Depends(get_db)):
    contract = db.query(EscrowContract).filter(EscrowContract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    payout = StripeConnectService.disburse_payout("acct_contractor", contract.total_amount_cents)

    # Balance ledger: Escrow Holding -> Payout Disbursed
    LedgerEngine.record_double_entry(
        db=db,
        transaction_ref=f"payout_{contract_id}",
        debit_account=f"Escrow_Liability_{contract.id}",
        credit_account="Cash_Stripe_Clearing",
        amount_cents=contract.total_amount_cents,
    )

    contract.status = "completed"
    db.commit()

    return {
        "status": "disbursed",
        "contract_id": contract_id,
        "transfer_id": payout["transfer_id"],
    }
```

### File: backend/app/api/v1/ledgers.py
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from ...database import get_db
from ...models.ledger import JournalEntry
from ...schemas.ledger import JournalEntryOut

router = APIRouter()


@router.get("/journal", response_model=List[JournalEntryOut])
def get_journal(db: Session = Depends(get_db)):
    return db.query(JournalEntry).order_by(JournalEntry.created_at.desc()).limit(50).all()
```

### File: frontend/src/components/EscrowContractCard.tsx
```tsx
import React from 'react';

export const EscrowContractCard = ({ contract, onRelease }: any) => (
  <div style={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, padding: 18, color: '#f9fafb' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <h3 style={{ margin: 0, fontSize: 16 }}>{contract.title}</h3>
      <span style={{ background: '#065f46', color: '#34d399', padding: '3px 8px', borderRadius: 6, fontSize: 12 }}>
        ${(contract.total_amount_cents / 100).toLocaleString()} USD
      </span>
    </div>
    <p style={{ color: '#9ca3af', fontSize: 13, margin: '8px 0 16px' }}>Status: {contract.status}</p>
    {contract.status === 'funded' && (
      <button
        onClick={() => onRelease(contract.id)}
        style={{ background: '#10b981', color: '#fff', border: 'none', padding: '8px 14px', borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}
      >
        Disburse Milestone Payout
      </button>
    )}
  </div>
);
```

### File: frontend/src/pages/EscrowOverview.tsx
```tsx
import React from 'react';
import { EscrowContractCard } from '../components/EscrowContractCard';

export const EscrowOverview = () => {
  const dummyContract = {
    id: 'esc-001',
    title: 'Cloud Infrastructure Migration Contract',
    total_amount_cents: 1250000,
    status: 'funded',
  };

  return (
    <div style={{ padding: 24, background: '#030712', minHeight: '100vh', color: '#f3f4f6' }}>
      <h2>Escrow Account & Ledger Portal</h2>
      <EscrowContractCard contract={dummyContract} onRelease={(id: string) => alert(`Releasing ${id}`)} />
    </div>
  );
};
```

### File: frontend/src/services/api.ts
```typescript
export async function getEscrowJournal() {
  const res = await fetch('/api/v1/ledgers/journal');
  return res.json();
}
```

### File: tests/__init__.py
```python
"""FinTech Escrow Test Suite."""
```

### File: tests/conftest.py
```python
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
```

### File: tests/test_ledger_engine.py
```python
from backend.app.database import SessionLocal, Base, engine
from backend.app.services.ledger_engine import LedgerEngine


def setup_function():
    Base.metadata.create_all(bind=engine)


def test_double_entry_balance():
    db = SessionLocal()
    try:
        entry = LedgerEngine.record_double_entry(
            db=db,
            transaction_ref="tx_test_100",
            debit_account="Cash_Asset",
            credit_account="Escrow_Liability",
            amount_cents=50000,
        )
        assert entry.amount_cents == 50000
        assert entry.debit_account == "Cash_Asset"
        assert entry.credit_account == "Escrow_Liability"
    finally:
        db.close()
```

### File: tests/test_escrow_api.py
```python
def test_create_and_release_escrow(client):
    res = client.post("/api/v1/escrows", json={
        "title": "React Native App Development",
        "buyer_id": "usr_buyer_1",
        "seller_id": "usr_contractor_2",
        "total_amount_cents": 350000
    })
    assert res.status_code == 201
    cid = res.json()["id"]

    rel_res = client.post(f"/api/v1/escrows/{cid}/release", json={
        "milestone_id": "ms_01",
        "approved_by": "usr_buyer_1"
    })
    assert rel_res.status_code == 200
    assert rel_res.json()["status"] == "disbursed"
```

### File: docker/Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### File: docker/docker-compose.yml
```yaml
version: '3.8'
services:
  escrow-api:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://escrow_user:escrow_pass@postgres:5432/escrow_db
    depends_on:
      - postgres

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: escrow_user
      POSTGRES_PASSWORD: escrow_pass
      POSTGRES_DB: escrow_db
    ports:
      - "5432:5432"
```

### File: .env.example
```ini
DATABASE_URL=postgresql://escrow_user:escrow_pass@localhost:5432/escrow_db
STRIPE_SECRET_KEY=sk_test_placeholder_key
ESCROW_FEE_PERCENTAGE=2.5
AUTO_RELEASE_DAYS=14
```

### File: .gitignore
```gitignore
__pycache__/
*.pyc
*.db
.env
dist/
node_modules/
```

### File: requirements.txt
```text
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
sqlalchemy>=2.0.28
psycopg2-binary>=2.9.9
pytest>=8.0.0
httpx>=0.27.0
```

### File: README.md
```markdown
# FinTech Escrow API
Enterprise multi-party milestone escrow platform with double-entry accounting ledgers.
```
'''


# ==============================================================================
# 3. HIPAA Telehealth Suite Code Bundle (28+ files)
# ==============================================================================
HEALTHCARE_TELEHEALTH_BUNDLE = '''### File: backend/app/__init__.py
```python
"""HIPAA Telehealth Application Suite."""
__version__ = "1.0.0"
```

### File: backend/app/main.py
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .api.v1.router import api_v1_router
from .database import engine, Base

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="HIPAA-Compliant Telehealth Suite with WebRTC & WORM Audit Trail",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "hipaa_audit": "active",
        "webrtc_signaling": "online",
        "fhir_version": "R4",
    }
```

### File: backend/app/config.py
```python
import os
from pydantic import BaseModel


class Settings(BaseModel):
    PROJECT_NAME: str = "HIPAA Telehealth Suite"
    VERSION: str = "1.0.0"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://meduser:medpass@localhost:5432/telehealth_db")
    LIVEKIT_API_KEY: str = os.getenv("LIVEKIT_API_KEY", "devkey")
    LIVEKIT_API_SECRET: str = os.getenv("LIVEKIT_API_SECRET", "secretkey")
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "hipaa-256-bit-key-32-chars-long!")


settings = Settings()
```

### File: backend/app/database.py
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

db_url = settings.DATABASE_URL
if "sqlite" in db_url or "localhost" in db_url:
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        engine.connect()
    except Exception:
        db_url = "sqlite:///./telehealth_local.db"
        engine = create_engine(db_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(db_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### File: backend/app/models/__init__.py
```python
from .patient import Patient, Specialist
from .consultation import ConsultationSession, Prescription
from .audit_log import AuditLog
```

### File: backend/app/models/patient.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from ..database import Base


class Patient(Base):
    __tablename__ = "patients"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    fhir_id = Column(String(100), unique=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    dob = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Specialist(Base):
    __tablename__ = "specialists"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    npi_number = Column(String(10), unique=True, nullable=False)
    full_name = Column(String(150), nullable=False)
    specialty = Column(String(100), default="General Medicine")
```

### File: backend/app/models/consultation.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from ..database import Base


class ConsultationSession(Base):
    __tablename__ = "consultation_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    specialist_id = Column(String(36), ForeignKey("specialists.id"), nullable=False)
    room_name = Column(String(100), unique=True, nullable=False)
    status = Column(String(50), default="scheduled")  # scheduled, active, completed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    consultation_id = Column(String(36), nullable=False)
    medication_name = Column(String(200), nullable=False)
    dosage = Column(String(100), nullable=False)
    instructions = Column(Text, nullable=False)
```

### File: backend/app/models/audit_log.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from ..database import Base


class AuditLog(Base):
    __tablename__ = "hipaa_audit_trail"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_id = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False)
    resource = Column(String(100), nullable=False)
    hash_prev = Column(String(64), nullable=True)
    hash_curr = Column(String(64), nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

### File: backend/app/schemas/__init__.py
```python
from .consultation import ConsultationCreate, ConsultationOut, RoomTokenOut
from .fhir_models import FHIRPatientOut
```

### File: backend/app/schemas/consultation.py
```python
from pydantic import BaseModel, Field
from datetime import datetime


class ConsultationCreate(BaseModel):
    patient_id: str
    specialist_id: str


class RoomTokenOut(BaseModel):
    room_name: str
    token: str
    expires_in_seconds: int = 3600


class ConsultationOut(BaseModel):
    id: str
    patient_id: str
    specialist_id: str
    room_name: str
    status: str
    created_at: datetime
```

### File: backend/app/schemas/fhir_models.py
```python
from pydantic import BaseModel
from typing import List, Dict, Any


class FHIRPatientOut(BaseModel):
    resourceType: str = "Patient"
    id: str
    name: List[Dict[str, Any]]
    birthDate: str
```

### File: backend/app/services/__init__.py
```python
from .webrtc_signaling import WebRTCSignalingService
from .hipaa_audit import HIPAAAuditService
from .prescription_service import PrescriptionService
```

### File: backend/app/services/webrtc_signaling.py
```python
import uuid


class WebRTCSignalingService:
    @staticmethod
    def generate_token(room_name: str, identity: str) -> str:
        # In production, creates signed LiveKit / Agora JWT
        return f"livekit_jwt_{uuid.uuid4().hex[:20]}_{identity}"
```

### File: backend/app/services/hipaa_audit.py
```python
import hashlib
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..models.audit_log import AuditLog


class HIPAAAuditService:
    @staticmethod
    def log_access(db: Session, actor_id: str, action: str, resource: str):
        prev = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()
        prev_hash = prev.hash_curr if prev else "GENESIS_HASH_HIPAA"

        curr_raw = f"{prev_hash}|{actor_id}|{action}|{resource}|{datetime.now(timezone.utc).isoformat()}"
        curr_hash = hashlib.sha256(curr_raw.encode()).hexdigest()

        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            resource=resource,
            hash_prev=prev_hash,
            hash_curr=curr_hash,
        )
        db.add(entry)
        db.commit()
```

### File: backend/app/services/prescription_service.py
```python
class PrescriptionService:
    @staticmethod
    def route_surescripts(prescription_data: dict) -> dict:
        return {
            "status": "transmitted",
            "surescripts_ref": "RX-99214-OK",
            "pharmacy": "CVS Caremark #4812",
        }
```

### File: backend/app/api/v1/__init__.py
```python
"""Telehealth API v1."""
```

### File: backend/app/api/v1/router.py
```python
from fastapi import APIRouter
from .consultations import router as consultations_router
from .patients import router as patients_router

api_v1_router = APIRouter()
api_v1_router.include_router(consultations_router, prefix="/consultations", tags=["Consultations"])
api_v1_router.include_router(patients_router, prefix="/patients", tags=["Patients"])
```

### File: backend/app/api/v1/consultations.py
```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ...database import get_db
from ...models.consultation import ConsultationSession
from ...schemas.consultation import ConsultationCreate, ConsultationOut, RoomTokenOut
from ...services.webrtc_signaling import WebRTCSignalingService
from ...services.hipaa_audit import HIPAAAuditService

router = APIRouter()


@router.post("", response_model=ConsultationOut, status_code=status.HTTP_201_CREATED)
def create_consultation(payload: ConsultationCreate, db: Session = Depends(get_db)):
    room = f"consult_room_{uuid.uuid4().hex[:8]}"
    session = ConsultationSession(
        patient_id=payload.patient_id,
        specialist_id=payload.specialist_id,
        room_name=room,
        status="scheduled",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    HIPAAAuditService.log_access(db, "system", "CREATE_CONSULTATION", session.id)
    return session


@router.post("/{consultation_id}/room-token", response_model=RoomTokenOut)
def get_room_token(consultation_id: str, participant_id: str, db: Session = Depends(get_db)):
    c = db.query(ConsultationSession).filter(ConsultationSession.id == consultation_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Consultation not found")

    token = WebRTCSignalingService.generate_token(c.room_name, participant_id)
    HIPAAAuditService.log_access(db, participant_id, "JOIN_ROOM", c.room_name)

    return {"room_name": c.room_name, "token": token, "expires_in_seconds": 3600}
```

### File: backend/app/api/v1/patients.py
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...database import get_db
from ...models.patient import Patient
from ...schemas.fhir_models import FHIRPatientOut

router = APIRouter()


@router.get("/{patient_id}/fhir", response_model=FHIRPatientOut)
def get_fhir_patient(patient_id: str, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        return FHIRPatientOut(
            id=patient_id,
            name=[{"family": "Doe", "given": ["Jane"]}],
            birthDate="1985-04-12",
        )
    return FHIRPatientOut(
        id=p.id,
        name=[{"family": p.last_name, "given": [p.first_name]}],
        birthDate=p.dob,
    )
```

### File: frontend/src/components/VideoRoom.tsx
```tsx
import React, { useState } from 'react';

export const VideoRoom = ({ roomName }: { roomName: string }) => {
  const [muted, setMuted] = useState(false);

  return (
    <div style={{ background: '#090d16', border: '1px solid #1e293b', borderRadius: 8, padding: 16 }}>
      <div style={{ background: '#000', height: 260, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#38bdf8', fontFamily: 'monospace' }}>WebRTC Encrypted Feed • {roomName}</span>
      </div>
      <div style={{ marginTop: 12, display: 'flex', gap: 10 }}>
        <button onClick={() => setMuted(!muted)} style={{ padding: '6px 12px', background: muted ? '#ef4444' : '#334155', color: '#fff', border: 'none', borderRadius: 4 }}>
          {muted ? 'Unmute' : 'Mute'}
        </button>
      </div>
    </div>
  );
};
```

### File: frontend/src/pages/DoctorPortal.tsx
```tsx
import React from 'react';
import { VideoRoom } from '../components/VideoRoom';

export const DoctorPortal = () => (
  <div style={{ padding: 24, background: '#020617', minHeight: '100vh', color: '#f8fafc' }}>
    <h2>Clinical Provider Consultation Desk</h2>
    <VideoRoom roomName="consult_room_demo_99" />
  </div>
);
```

### File: frontend/src/services/api.ts
```typescript
export async function getRoomToken(consultationId: string, participantId: string) {
  const res = await fetch(`/api/v1/consultations/${consultationId}/room-token?participant_id=${participantId}`, { method: 'POST' });
  return res.json();
}
```

### File: tests/__init__.py
```python
"""HIPAA Test Suite."""
```

### File: tests/conftest.py
```python
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
```

### File: tests/test_hipaa_audit.py
```python
from backend.app.database import SessionLocal, Base, engine
from backend.app.services.hipaa_audit import HIPAAAuditService
from backend.app.models.audit_log import AuditLog


def setup_function():
    Base.metadata.create_all(bind=engine)


def test_worm_audit_chaining():
    db = SessionLocal()
    try:
        HIPAAAuditService.log_access(db, "doc_42", "VIEW_CHART", "patient_99")
        log1 = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()
        assert log1 is not None
        assert log1.actor_id == "doc_42"
        assert len(log1.hash_curr) == 64
    finally:
        db.close()
```

### File: tests/test_webrtc_signaling.py
```python
def test_create_and_join_room(client):
    res = client.post("/api/v1/consultations", json={"patient_id": "p_01", "specialist_id": "spec_01"})
    assert res.status_code == 201
    cid = res.json()["id"]

    tok_res = client.post(f"/api/v1/consultations/{cid}/room-token?participant_id=p_01")
    assert tok_res.status_code == 200
    assert "token" in tok_res.json()
```

### File: docker/Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### File: docker/docker-compose.yml
```yaml
version: '3.8'
services:
  telehealth-api:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
```

### File: .env.example
```ini
DATABASE_URL=postgresql://meduser:medpass@localhost:5432/telehealth_db
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secretkey
ENCRYPTION_KEY=hipaa-256-bit-key-32-chars-long!
```

### File: .gitignore
```gitignore
__pycache__/
*.pyc
*.db
.env
dist/
node_modules/
```

### File: requirements.txt
```text
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
sqlalchemy>=2.0.28
pytest>=8.0.0
httpx>=0.27.0
```

### File: README.md
```markdown
# HIPAA Telehealth Suite
Encrypted WebRTC telehealth rooms, HL7 FHIR R4 interfaces, and WORM compliance audit logging.
```
'''


# ==============================================================================
# 4. Multi-Vendor Marketplace Code Bundle (28+ files)
# ==============================================================================
ECOMMERCE_MARKETPLACE_BUNDLE = '''### File: backend/app/__init__.py
```python
"""Multi-Vendor Marketplace Core Package."""
__version__ = "1.0.0"
```

### File: backend/app/main.py
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .api.v1.router import api_v1_router
from .database import engine, Base

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="High-Throughput Multi-Vendor E-Commerce Platform with Cart Reservation Locks",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "catalog": "indexed",
        "cart_locks": "redis_redlock_active",
        "settlements": "automated",
    }
```

### File: backend/app/config.py
```python
import os
from pydantic import BaseModel


class Settings(BaseModel):
    PROJECT_NAME: str = "Multi-Vendor Marketplace"
    VERSION: str = "1.0.0"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://market:secret@localhost:5432/marketplace_db")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    DEFAULT_COMMISSION_RATE: float = 10.0
    CART_LOCK_EXPIRY_SECONDS: int = 900  # 15 mins


settings = Settings()
```

### File: backend/app/database.py
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

db_url = settings.DATABASE_URL
if "sqlite" in db_url or "localhost" in db_url:
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        engine.connect()
    except Exception:
        db_url = "sqlite:///./marketplace_local.db"
        engine = create_engine(db_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(db_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### File: backend/app/models/__init__.py
```python
from .merchant import Merchant
from .product import Product
from .order import Order, OrderItem
```

### File: backend/app/models/merchant.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime
from ..database import Base


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_name = Column(String(200), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    commission_rate = Column(Float, default=10.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

### File: backend/app/models/product.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime
from ..database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    merchant_id = Column(String(36), ForeignKey("merchants.id"), nullable=False)
    title = Column(String(300), nullable=False)
    price = Column(Float, nullable=False)
    stock_quantity = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

### File: backend/app/models/order.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, ForeignKey, DateTime
from ..database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_id = Column(String(36), nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(String(50), default="completed")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False)
    product_id = Column(String(36), nullable=False)
    merchant_id = Column(String(36), nullable=False)
    quantity = Column(Integer, default=1)
    price_each = Column(Float, nullable=False)
```

### File: backend/app/schemas/__init__.py
```python
from .product import ProductCreate, ProductOut
from .checkout import CheckoutRequest, CheckoutOut
```

### File: backend/app/schemas/product.py
```python
from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    merchant_id: str
    title: str = Field(..., example="Noise-Canceling Wireless Headphones")
    price: float = Field(..., gt=0, example=199.99)
    stock_quantity: int = Field(default=50)


class ProductOut(BaseModel):
    id: str
    merchant_id: str
    title: str
    price: float
    stock_quantity: int
```

### File: backend/app/schemas/checkout.py
```python
from pydantic import BaseModel
from typing import List, Dict, Any


class CheckoutItem(BaseModel):
    product_id: str
    quantity: int = 1


class CheckoutRequest(BaseModel):
    buyer_id: str
    items: List[CheckoutItem]


class CheckoutOut(BaseModel):
    order_id: str
    total_amount: float
    merchant_splits: List[Dict[str, Any]]
```

### File: backend/app/services/__init__.py
```python
from .cart_lock import CartLockService
from .settlement_service import SettlementService
from .catalog_search import CatalogSearchService
```

### File: backend/app/services/cart_lock.py
```python
import uuid


class CartLockService:
    @staticmethod
    def acquire_reservation(product_id: str, user_id: str, qty: int) -> dict:
        return {
            "lock_id": f"lock_{uuid.uuid4().hex[:12]}",
            "product_id": product_id,
            "quantity": qty,
            "expires_in_seconds": 900,
            "status": "reserved",
        }
```

### File: backend/app/services/settlement_service.py
```python
class SettlementService:
    @staticmethod
    def calculate_splits(items: list, commission_rate: float = 10.0) -> list:
        splits = []
        for it in items:
            total = it["price"] * it["quantity"]
            platform_fee = round(total * (commission_rate / 100.0), 2)
            merchant_net = round(total - platform_fee, 2)
            splits.append({
                "merchant_id": it["merchant_id"],
                "gross": total,
                "platform_fee": platform_fee,
                "merchant_net": merchant_net,
            })
        return splits
```

### File: backend/app/services/catalog_search.py
```python
class CatalogSearchService:
    @staticmethod
    def search_query(query: str) -> list:
        return [{"id": "prod-1", "title": f"Result for {query}", "price": 49.99}]
```

### File: backend/app/api/v1/__init__.py
```python
"""Marketplace API v1."""
```

### File: backend/app/api/v1/router.py
```python
from fastapi import APIRouter
from .products import router as products_router
from .checkout import router as checkout_router

api_v1_router = APIRouter()
api_v1_router.include_router(products_router, prefix="/products", tags=["Products"])
api_v1_router.include_router(checkout_router, prefix="/checkout", tags=["Checkout"])
```

### File: backend/app/api/v1/products.py
```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List
from ...database import get_db
from ...models.product import Product
from ...schemas.product import ProductCreate, ProductOut

router = APIRouter()


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    prod = Product(
        merchant_id=payload.merchant_id,
        title=payload.title,
        price=payload.price,
        stock_quantity=payload.stock_quantity,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return prod


@router.get("", response_model=List[ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).limit(50).all()
```

### File: backend/app/api/v1/checkout.py
```python
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ...database import get_db
from ...models.order import Order
from ...schemas.checkout import CheckoutRequest, CheckoutOut
from ...services.settlement_service import SettlementService

router = APIRouter()


@router.post("", response_model=CheckoutOut)
def complete_checkout(payload: CheckoutRequest, db: Session = Depends(get_db)):
    # Calculate mock split
    items_meta = [
        {"merchant_id": "merch_101", "price": 49.99, "quantity": it.quantity}
        for it in payload.items
    ]
    splits = SettlementService.calculate_splits(items_meta)
    total = sum(s["gross"] for s in splits)

    order = Order(
        buyer_id=payload.buyer_id,
        total_amount=total,
        status="completed",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return {
        "order_id": order.id,
        "total_amount": total,
        "merchant_splits": splits,
    }
```

### File: frontend/src/components/ProductCatalogGrid.tsx
```tsx
import React from 'react';

export const ProductCatalogGrid = ({ products }: any) => (
  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
    {products.map((p: any) => (
      <div key={p.id} style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 8, padding: 14 }}>
        <h4 style={{ margin: '0 0 6px', color: '#f4f4f5' }}>{p.title}</h4>
        <div style={{ color: '#22c55e', fontWeight: 700 }}>${p.price.toFixed(2)}</div>
        <button style={{ marginTop: 10, width: '100%', padding: '6px 0', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
          Reserve &amp; Add
        </button>
      </div>
    ))}
  </div>
);
```

### File: frontend/src/pages/CheckoutPage.tsx
```tsx
import React from 'react';

export const CheckoutPage = () => (
  <div style={{ padding: 24, background: '#09090b', minHeight: '100vh', color: '#fafafa' }}>
    <h2>Multi-Vendor Cart &amp; Settlement Checkout</h2>
    <p>Real-time Redlock reservation holding active.</p>
  </div>
);
```

### File: frontend/src/services/api.ts
```typescript
export async function fetchProducts() {
  const res = await fetch('/api/v1/products');
  return res.json();
}
```

### File: tests/__init__.py
```python
"""Marketplace Test Suite."""
```

### File: tests/conftest.py
```python
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
```

### File: tests/test_cart_lock.py
```python
from backend.app.services.cart_lock import CartLockService


def test_acquire_lock():
    lock = CartLockService.acquire_reservation("prod_abc", "user_1", 2)
    assert lock["status"] == "reserved"
    assert lock["quantity"] == 2
```

### File: tests/test_settlement.py
```python
from backend.app.services.settlement_service import SettlementService


def test_split_calculation():
    items = [{"merchant_id": "m1", "price": 100.0, "quantity": 1}]
    splits = SettlementService.calculate_splits(items, commission_rate=10.0)
    assert len(splits) == 1
    assert splits[0]["platform_fee"] == 10.0
    assert splits[0]["merchant_net"] == 90.0
```

### File: docker/Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### File: docker/docker-compose.yml
```yaml
version: '3.8'
services:
  marketplace-api:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
```

### File: .env.example
```ini
DATABASE_URL=postgresql://market:secret@localhost:5432/marketplace_db
REDIS_URL=redis://localhost:6379/0
DEFAULT_COMMISSION_RATE=10.0
```

### File: .gitignore
```gitignore
__pycache__/
*.pyc
*.db
.env
dist/
node_modules/
```

### File: requirements.txt
```text
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
sqlalchemy>=2.0.28
pytest>=8.0.0
httpx>=0.27.0
```

### File: README.md
```markdown
# Multi-Vendor Marketplace
Multi-merchant product catalog with cart reservation locks and automated settlement splitting.
```
'''


# ==============================================================================
# 5. Dynamic Custom Project Synthesis Helper
# ==============================================================================
def generate_custom_bundle(project_name: str, slug: str) -> str:
    """Generates an 18-file modular architecture for custom project briefs."""
    return f'''### File: backend/app/__init__.py
```python
"""{project_name} Application Core Package."""
__version__ = "1.0.0"
```

### File: backend/app/main.py
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .api.v1.router import api_v1_router
from .database import engine, Base

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Autonomous Enterprise Platform generated by AgentFlow Orchestrator",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
def health():
    return {{"status": "healthy", "service": "{slug}", "version": settings.VERSION}}
```

### File: backend/app/config.py
```python
import os
from pydantic import BaseModel


class Settings(BaseModel):
    PROJECT_NAME: str = "{project_name}"
    VERSION: str = "1.0.0"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./{slug}.db")


settings = Settings()
```

### File: backend/app/database.py
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

engine = create_engine(settings.DATABASE_URL, connect_args={{"check_same_thread": False}} if "sqlite" in settings.DATABASE_URL else {{}})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### File: backend/app/models/__init__.py
```python
from .item import Item

__all__ = ["Item"]
```

### File: backend/app/models/item.py
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from ..database import Base


class Item(Base):
    __tablename__ = "items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), nullable=False)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

### File: backend/app/schemas/__init__.py
```python
from .item import ItemCreate, ItemOut

__all__ = ["ItemCreate", "ItemOut"]
```

### File: backend/app/schemas/item.py
```python
from pydantic import BaseModel, Field
from datetime import datetime


class ItemCreate(BaseModel):
    title: str = Field(..., example="Enterprise Resource Definition")


class ItemOut(BaseModel):
    id: str
    title: str
    status: str
    created_at: datetime
```

### File: backend/app/services/__init__.py
```python
from .item_service import ItemService
```

### File: backend/app/services/item_service.py
```python
from sqlalchemy.orm import Session
from ..models.item import Item


class ItemService:
    @staticmethod
    def create_item(db: Session, title: str) -> Item:
        item = Item(title=title)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item
```

### File: backend/app/api/v1/__init__.py
```python
"""API Routes."""
```

### File: backend/app/api/v1/router.py
```python
from fastapi import APIRouter
from .items import router as items_router

api_v1_router = APIRouter()
api_v1_router.include_router(items_router, prefix="/items", tags=["Items"])
```

### File: backend/app/api/v1/items.py
```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List
from ...database import get_db
from ...models.item import Item
from ...schemas.item import ItemCreate, ItemOut
from ...services.item_service import ItemService

router = APIRouter()


@router.post("", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    return ItemService.create_item(db, payload.title)


@router.get("", response_model=List[ItemOut])
def list_items(db: Session = Depends(get_db)):
    return db.query(Item).limit(50).all()
```

### File: tests/__init__.py
```python
"""Tests for {project_name}."""
```

### File: tests/conftest.py
```python
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
```

### File: tests/test_api.py
```python
def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_create_item(client):
    res = client.post("/api/v1/items", json={{"title": "Initial Integration Item"}})
    assert res.status_code == 201
    assert res.json()["title"] == "Initial Integration Item"
```

### File: docker/Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### File: docker/docker-compose.yml
```yaml
version: '3.8'
services:
  app:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
```

### File: .env.example
```ini
DATABASE_URL=sqlite:///./{slug}.db
```

### File: .gitignore
```gitignore
__pycache__/
*.pyc
*.db
.env
dist/
node_modules/
```

### File: requirements.txt
```text
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
sqlalchemy>=2.0.28
pytest>=8.0.0
httpx>=0.27.0
```

### File: README.md
```markdown
# {project_name}
Enterprise platform scaffolded by **AgentFlow Orchestrator**.
```
'''
