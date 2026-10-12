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


def test_scan_new_owasp_rules():
    vulnerable_snippet = '''
import pickle
import requests

def load_payload(raw_data):
    return pickle.loads(raw_data)

def fetch_external(url):
    return requests.get(url)

def run_agent(user_prompt):
    return f"System: You are an agent. User Prompt: {user_prompt}"
'''
    findings = _scan_text_content("app/agent.py", vulnerable_snippet)
    cwe_list = [f["cwe_id"] for f in findings]
    assert "CWE-502" in cwe_list  # Insecure Deserialization
    assert "CWE-918" in cwe_list  # SSRF
    assert "CWE-20" in cwe_list   # Prompt Injection


def test_scan_advanced_security_rules():
    vulnerable_snippet = '''
import jwt
import logging

DATABASE_URL = "postgres://root:password@localhost:5432/production_db"

def verify_token(token):
    # None algorithm bypass
    return jwt.decode(token, verify=False, algorithms=["none"])

def handle_login(user, password):
    logging.info(f"User login attempt: {user} with password: {password}")
    return True
'''
    findings = _scan_text_content("app/auth.py", vulnerable_snippet)
    cwe_list = [f["cwe_id"] for f in findings]
    rule_ids = [f.get("rule_id") for f in findings]

    assert "CWE-345" in cwe_list or "SEC-OWASP-10" in rule_ids  # Insecure JWT
    assert "CWE-200" in cwe_list or "SEC-CONFIG-01" in rule_ids # Default DB credentials
    assert "CWE-532" in cwe_list or "SEC-LOG-01" in rule_ids    # Credential logging

    # Verify enrichment fields exist
    for f in findings:
        assert "layer" in f
        assert "suggested_patch" in f
        assert "effort_estimate" in f
        assert f["layer"] in ["Application", "Data Tier", "Infrastructure", "Perimeter", "Cryptography", "AI Safety"]


def test_scan_dockerfile_rules():
    docker_snippet = '''
FROM python:3.11-slim
WORKDIR /app
COPY . .
USER root
CMD ["python", "main.py"]
'''
    findings = _scan_text_content("Dockerfile", docker_snippet)
    rule_ids = [f.get("rule_id") for f in findings]
    assert "SEC-DOCKER-01" in rule_ids
    root_finding = next(f for f in findings if f.get("rule_id") == "SEC-DOCKER-01")
    assert root_finding["layer"] == "Infrastructure"
    assert "USER appuser" in root_finding["suggested_patch"]


def test_security_analysis_api_integration():
    # 1. Create a project
    p_res = client.post("/projects/", json={
        "name": "FinTech Threat Model Microservice",
        "brief": "Secure payments gateway with bank integrations and JWT authorization."
    })
    assert p_res.status_code == 200
    p_id = p_res.json()["id"]

    # 2. Call security analysis
    analysis_res = client.get(f"/projects/{p_id}/security-analysis")
    assert analysis_res.status_code == 200
    analysis = analysis_res.json()

    assert analysis["audit_report"]["project_name"] == "FinTech Threat Model Microservice"
    assert "attack_surface" in analysis
    assert "stride_threats" in analysis
    assert "defense_in_depth_layers" in analysis
    assert "compliance_frameworks" in analysis

    # Attack surface validations
    surface = analysis["attack_surface"]
    assert "public_routes_count" in surface
    assert "authenticated_routes_count" in surface
    assert "attack_surface_rating" in surface
    assert surface["attack_surface_rating"] in ["MINIMAL", "LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"]
    assert "key_exposure_vectors" in surface

    # STRIDE matrix validations (should cover all 6 STRIDE categories)
    stride_categories = {t["category"] for t in analysis["stride_threats"]}
    assert "Spoofing" in stride_categories
    assert "Tampering" in stride_categories
    assert "Repudiation" in stride_categories
    assert "Information Disclosure" in stride_categories
    assert "Denial of Service" in stride_categories
    assert "Elevation of Privilege" in stride_categories

    # Defense in Depth layers
    layers = analysis["defense_in_depth_layers"]
    assert isinstance(layers, dict)
    assert "Application" in layers
    assert "Data Tier" in layers
    assert "Infrastructure" in layers

    # Compliance frameworks
    compliance = analysis["compliance_frameworks"]
    assert len(compliance) >= 3
    framework_names = {c["framework"] for c in compliance}
    assert any("OWASP ASVS" in n for n in framework_names)
    assert any("SOC 2" in n for n in framework_names)
    assert any("CIS Controls" in n for n in framework_names)


def test_security_report_pdf_generation():
    # 1. Create a project
    p_res = client.post("/projects/", json={
        "name": "CyberShield Health Gateway",
        "brief": "HIPAA and SOC 2 compliant healthcare API gateway with audit trails."
    })
    assert p_res.status_code == 200
    p_id = p_res.json()["id"]

    # 2. Test Dark Theme PDF Download
    dark_pdf_res = client.get(f"/projects/{p_id}/security-report-pdf?theme=dark")
    assert dark_pdf_res.status_code == 200
    assert dark_pdf_res.headers["content-type"] == "application/pdf"
    assert "attachment" in dark_pdf_res.headers["content-disposition"]
    assert dark_pdf_res.content.startswith(b"%PDF-")
    assert len(dark_pdf_res.content) > 3000

    # 3. Test Light Theme PDF Download
    light_pdf_res = client.get(f"/projects/{p_id}/security-report-pdf?theme=light")
    assert light_pdf_res.status_code == 200
    assert light_pdf_res.headers["content-type"] == "application/pdf"
    assert "attachment" in light_pdf_res.headers["content-disposition"]
    assert light_pdf_res.content.startswith(b"%PDF-")
    assert len(light_pdf_res.content) > 3000

    # 4. Test Preview PDF (Inline content disposition)
    preview_res = client.get(f"/projects/{p_id}/preview-security-report-pdf?theme=dark")
    assert preview_res.status_code == 200
    assert preview_res.headers["content-type"] == "application/pdf"
    assert "inline" in preview_res.headers["content-disposition"]
    assert preview_res.content.startswith(b"%PDF-")
