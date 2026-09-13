import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agents.security_scanner import _scan_text_content, run_project_security_audit

client = TestClient(app)


def test_scan_text_content_vulnerabilities():
    vulnerable_code = """
import os
import hashlib

SECRET_KEY = "my_super_secret_12345"
DEBUG = True
allow_origins = ["*"]

def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    return db.execute(query)

def calc_hash(val):
    return hashlib.md5(val.encode()).hexdigest()

def execute_calc(expr):
    return eval(expr)
"""
    findings = _scan_text_content("app/main.py", vulnerable_code)
    assert len(findings) >= 5

    cwe_list = [f["cwe_id"] for f in findings]
    assert "CWE-798" in cwe_list  # Hardcoded secret
    assert "CWE-89" in cwe_list   # SQL injection
    assert "CWE-942" in cwe_list  # Wildcard CORS
    assert "CWE-489" in cwe_list  # DEBUG=True
    assert "CWE-95" in cwe_list   # eval


def test_scan_clean_code():
    clean_code = """
import os
import hashlib

SECRET_KEY = os.getenv("SECRET_KEY", "default_safe")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
allow_origins = ["https://app.example.com"]

def get_user(db, user_id):
    return db.query(User).filter(User.id == user_id).first()

def calc_hash(val):
    return hashlib.sha256(val.encode()).hexdigest()
"""
    findings = _scan_text_content("app/main.py", clean_code)
    critical_or_high = [f for f in findings if f["severity"] in ["CRITICAL", "HIGH"]]
    assert len(critical_or_high) == 0


def test_security_audit_api_integration():
    # 1. Create a project
    p_res = client.post("/projects/", json={
        "name": "Secured FinTech Service",
        "brief": "Secure payment processing API with strict JWT authentication and parameterized SQL."
    })
    assert p_res.status_code == 200
    p_id = p_res.json()["id"]

    # Generate artifacts
    gen_res = client.post(f"/projects/{p_id}/generate")
    assert gen_res.status_code == 200

    # 2. Run security audit
    audit_res = client.get(f"/projects/{p_id}/security-audit")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()

    assert "overall_score" in audit_data
    assert "security_grade" in audit_data
    assert "severity_counts" in audit_data
    assert "vulnerabilities" in audit_data
    assert audit_data["project_name"] == "Secured FinTech Service"
    assert audit_data["overall_score"] >= 70
    assert audit_data["security_grade"] in ["A+", "A", "B"]

    # 3. Test POST trigger
    post_res = client.post(f"/projects/{p_id}/run-security-audit")
    assert post_res.status_code == 200
    assert post_res.json()["overall_score"] == audit_data["overall_score"]
