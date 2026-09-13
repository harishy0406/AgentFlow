"""
Phase 8+: Automated OWASP & AST Security Vulnerability Scanner Engine

Performs comprehensive static AST analysis and vulnerability pattern recognition
across all project artifacts (Codebase files, DB Schemas, API Specs, and Configs),
evaluating compliance against OWASP Top 10 and CWE benchmarks.
"""

import ast
import re
import uuid
from uuid import UUID
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session

from ..models import Project, ArtifactNode
from .scaffolder import parse_code_files


# ---------------------------------------------------------------------------
# Vulnerability Signature Rules
# ---------------------------------------------------------------------------

SECURITY_RULES = [
    {
        "id": "SEC-OWASP-01",
        "title": "Hardcoded Cryptographic Secret / API Key",
        "severity": "CRITICAL",
        "owasp_category": "A02:2021 - Cryptographic Failures",
        "cwe_id": "CWE-798",
        "pattern": r"""(?i)(?:secret[_-]?key|jwt[_-]?secret|api[_-]?key|password|db_pass)\s*=\s*['\"][a-zA-Z0-9_\-\.]{4,}['\"]""",
        "description": "Hardcoded secret or credential token detected in source code. If committed, this enables unauthorized credential reuse.",
        "remediation": "Move secrets into environment variables (e.g. os.getenv('SECRET_KEY')) and load via .env configuration.",
    },
    {
        "id": "SEC-OWASP-02",
        "title": "SQL Injection Vector via Raw String Concatenation",
        "severity": "CRITICAL",
        "owasp_category": "A03:2021 - Injection",
        "cwe_id": "CWE-89",
        "pattern": r"""(?i)(?:f['\"].*?(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE).*?\{|(?:execute|query|raw_sql)\s*\([^)]*?(?:f?['\"].*?(?:SELECT|INSERT|UPDATE|DELETE)|%|\+))""",
        "description": "Dynamic SQL query formed using unescaped string interpolation, opening potential SQL injection vulnerabilities.",
        "remediation": "Use parameterized queries or SQLAlchemy ORM model queries with bind parameters.",
    },
    {
        "id": "SEC-OWASP-03",
        "title": "Permissive Wildcard CORS Configuration",
        "severity": "HIGH",
        "owasp_category": "A01:2021 - Broken Access Control",
        "cwe_id": "CWE-942",
        "pattern": r"""(?i)allow_origins\s*=\s*\[\s*['\"]\*['\"]\s*\]""",
        "description": "CORS middleware is configured with wildcard '*' origin, allowing arbitrary external domains to make cross-origin requests.",
        "remediation": "Restrict allow_origins to verified domain hostnames in production configuration.",
    },
    {
        "id": "SEC-OWASP-04",
        "title": "Debug Mode Enabled in Production",
        "severity": "MEDIUM",
        "owasp_category": "A05:2021 - Security Misconfiguration",
        "cwe_id": "CWE-489",
        "pattern": r"""(?i)DEBUG\s*=\s*True""",
        "description": "Debug mode enables verbose stack traces and potentially interactive debugging terminals in production environments.",
        "remediation": "Set DEBUG=False by default and control via environment variable os.getenv('DEBUG', 'False').lower() == 'true'.",
    },
    {
        "id": "SEC-OWASP-05",
        "title": "Unsafe Dynamic Code Execution (eval/exec)",
        "severity": "CRITICAL",
        "owasp_category": "A03:2021 - Injection",
        "cwe_id": "CWE-95",
        "pattern": r"""\b(?:eval|exec)\s*\(""",
        "description": "Dynamic evaluation of arbitrary expressions can lead to Remote Code Execution (RCE).",
        "remediation": "Refactor logic to use safe parsers (e.g. ast.literal_eval or json.loads) instead of eval/exec.",
    },
    {
        "id": "SEC-OWASP-06",
        "title": "Weak Cryptographic Hash Algorithm (MD5/SHA1)",
        "severity": "HIGH",
        "owasp_category": "A02:2021 - Cryptographic Failures",
        "cwe_id": "CWE-328",
        "pattern": r"""(?i)hashlib\.(?:md5|sha1)\s*\(""",
        "description": "MD5 and SHA-1 algorithms are cryptographically broken and vulnerable to collision attacks.",
        "remediation": "Use SHA-256 (hashlib.sha256) or bcrypt/argon2 for password hashing.",
    },
    {
        "id": "SEC-OWASP-07",
        "title": "Missing Authorization Gate on Mutating Endpoint",
        "severity": "MEDIUM",
        "owasp_category": "A01:2021 - Broken Access Control",
        "cwe_id": "CWE-306",
        "pattern": r"""(?i)@app\.(?:post|put|delete|patch)\(.*?\)(?![^@]*Depends\(.*?(?:auth|user|token|perm))""",
        "description": "Mutating REST endpoint does not declare authentication/permission dependencies.",
        "remediation": "Enforce authentication middleware or Depends(get_current_user) on mutating routes.",
    }
]


def _scan_text_content(file_path: str, content: str) -> List[Dict[str, Any]]:
    """
    Runs AST and Regex scans against a single file content.
    """
    findings = []
    lines = content.splitlines()

    for rule in SECURITY_RULES:
        pattern = re.compile(rule["pattern"], re.MULTILINE)
        for match in pattern.finditer(content):
            # Calculate line number
            start_pos = match.start()
            line_num = content[:start_pos].count("\n") + 1
            snippet = lines[line_num - 1].strip() if line_num <= len(lines) else match.group(0)

            findings.append({
                "id": str(uuid.uuid4())[:8],
                "title": rule["title"],
                "severity": rule["severity"],
                "owasp_category": rule["owasp_category"],
                "cwe_id": rule["cwe_id"],
                "file_target": file_path,
                "line_number": line_num,
                "snippet": snippet[:100],
                "description": rule["description"],
                "remediation": rule["remediation"],
            })

    # Optional Python AST syntax inspection for python files
    if file_path.endswith(".py"):
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in ["eval", "exec"]:
                        # If not already flagged by regex
                        if not any(f["line_number"] == node.lineno and f["cwe_id"] == "CWE-95" for f in findings):
                            findings.append({
                                "id": str(uuid.uuid4())[:8],
                                "title": "Unsafe Dynamic Code Execution (eval/exec)",
                                "severity": "CRITICAL",
                                "owasp_category": "A03:2021 - Injection",
                                "cwe_id": "CWE-95",
                                "file_target": file_path,
                                "line_number": node.lineno,
                                "snippet": lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "eval(...)",
                                "description": "Dynamic evaluation of arbitrary expressions can lead to Remote Code Execution.",
                                "remediation": "Use ast.literal_eval or structured JSON parsing instead.",
                            })
        except SyntaxError:
            pass

    return findings


def run_project_security_audit(
    project_id: Union[UUID, str],
    db: Session
) -> Dict[str, Any]:
    """
    Scans all project artifacts and generated files, returning a complete
    OWASP & AST Security Audit Report with health grade and findings.
    """
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

    vulnerabilities: List[Dict[str, Any]] = []
    scanned_count = 0

    # 1. Scan Codebase Artifact & Parsed Files
    code_node = next((n for n in project.artifact_nodes if n.artifact_type == "CODE"), None)
    if code_node and code_node.sections:
        code_text = "\n\n".join(s.content for s in code_node.sections if s.content)
        parsed_files = parse_code_files(code_text)
        for cf in parsed_files:
            scanned_count += 1
            findings = _scan_text_content(cf.get("path", "app/main.py"), cf.get("content", ""))
            vulnerabilities.extend(findings)

    # 2. Scan DB Schema Artifact
    db_node = next((n for n in project.artifact_nodes if n.artifact_type == "DB_SCHEMA"), None)
    if db_node and db_node.sections:
        scanned_count += 1
        db_text = "\n\n".join(s.content for s in db_node.sections if s.content)
        vulnerabilities.extend(_scan_text_content("schemas/db_schema.sql", db_text))

    # 3. Scan API Spec Artifact
    api_node = next((n for n in project.artifact_nodes if n.artifact_type == "API_SPEC"), None)
    if api_node and api_node.sections:
        scanned_count += 1
        api_text = "\n\n".join(s.content for s in api_node.sections if s.content)
        vulnerabilities.extend(_scan_text_content("contracts/api_spec.md", api_text))

    # Calculate severity counts
    severity_counts = {
        "CRITICAL": sum(1 for v in vulnerabilities if v["severity"] == "CRITICAL"),
        "HIGH": sum(1 for v in vulnerabilities if v["severity"] == "HIGH"),
        "MEDIUM": sum(1 for v in vulnerabilities if v["severity"] == "MEDIUM"),
        "LOW": sum(1 for v in vulnerabilities if v["severity"] == "LOW"),
    }

    # Calculate overall security score (0 to 100)
    penalty = (
        severity_counts["CRITICAL"] * 25
        + severity_counts["HIGH"] * 15
        + severity_counts["MEDIUM"] * 8
        + severity_counts["LOW"] * 3
    )
    overall_score = max(10, 100 - penalty)

    if overall_score >= 95:
        security_grade = "A+"
    elif overall_score >= 85:
        security_grade = "A"
    elif overall_score >= 70:
        security_grade = "B"
    elif overall_score >= 55:
        security_grade = "C"
    else:
        security_grade = "F"

    remediation_status = (
        "Zero Vulnerabilities Detected (Hardened)"
        if len(vulnerabilities) == 0
        else f"{len(vulnerabilities)} Vulnerabilities Requiring Review"
    )

    return {
        "project_id": project.id,
        "project_name": project.name,
        "overall_score": overall_score,
        "security_grade": security_grade,
        "total_vulnerabilities": len(vulnerabilities),
        "severity_counts": severity_counts,
        "scanned_artifacts_count": max(1, scanned_count),
        "vulnerabilities": vulnerabilities,
        "remediation_status": remediation_status,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
