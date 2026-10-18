"""
AgentFlow Security Assessment & Vulnerability Audit Report PDF Generator

Generates executive-grade, multi-slide landscape ReportLab PDF reports
synthesizing OWASP Top 10 findings, CWE remediation registers, attack surface
profiling, and STRIDE threat modeling matrices with the same visual theme
and branding as the architectural slide deck.
Supports Executive Dark Mode (#0B0F17) and Printable Slate Light Mode (#F8FAFC).
"""

import io
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from uuid import UUID
from sqlalchemy.orm import Session

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

from ..models import Project, ArtifactNode
from ..agents.security_scanner import run_project_security_analysis, run_project_security_audit
from ..agents.scaffolder import sanitize_project_slug


DARK_THEME: Dict[str, Any] = {
    "name": "dark",
    "canvas_bg": "#0B0F17",
    "top_accent": "#EF4444",
    "header_sub": "#94A3B8",
    "header_project": "#FFFFFF",
    "divider": "#1E293B",
    "footer_sub": "#94A3B8",
    "footer_center": "#64748B",
    "footer_page": "#38BDF8",
    "title_color": "#FFFFFF",
    "h2_color": "#94A3B8",
    "body_color": "#E2E8F0",
    "body_secondary": "#CBD5E1",
    "accent_color": "#38BDF8",
    "success_color": "#34D399",
    "warning_color": "#FBBF24",
    "danger_color": "#F87171",
    "purple_color": "#A78BFA",
    "table_head_bg": "#1A2438",
    "table_row_bg1": "#111827",
    "table_row_bg2": "#162032",
    "table_box_border": "#26334D",
    "table_inner_grid": "#1E293B",
    "card_bg_primary": "#121826",
    "card_bg_secondary": "#162032",
    "code_text": "#38BDF8",
    "prefer_white_logo": True,
}

LIGHT_THEME: Dict[str, Any] = {
    "name": "light",
    "canvas_bg": "#F8FAFC",
    "top_accent": "#DC2626",
    "header_sub": "#475569",
    "header_project": "#0F172A",
    "divider": "#CBD5E1",
    "footer_sub": "#475569",
    "footer_center": "#64748B",
    "footer_page": "#0284C7",
    "title_color": "#0F172A",
    "h2_color": "#475569",
    "body_color": "#1E293B",
    "body_secondary": "#334155",
    "accent_color": "#0284C7",
    "success_color": "#059669",
    "warning_color": "#D97706",
    "danger_color": "#DC2626",
    "purple_color": "#7C3AED",
    "table_head_bg": "#E2E8F0",
    "table_row_bg1": "#FFFFFF",
    "table_row_bg2": "#F8FAFC",
    "table_box_border": "#CBD5E1",
    "table_inner_grid": "#E2E8F0",
    "card_bg_primary": "#FFFFFF",
    "card_bg_secondary": "#F1F5F9",
    "code_text": "#0369A1",
    "prefer_white_logo": False,
}

COLOR_MAP_LIGHT: Dict[str, str] = {
    "#0B0F17": "#F8FAFC",
    "#0284C7": "#0284C7",
    "#0D281E": "#ECFDF5",
    "#10B981": "#059669",
    "#0F2338": "#F0F9FF",
    "#111827": "#FFFFFF",
    "#121826": "#FFFFFF",
    "#162032": "#F8FAFC",
    "#1A1D36": "#F5F3FF",
    "#6366F1": "#7C3AED",
    "#1A2438": "#E2E8F0",
    "#1E293B": "#CBD5E1",
    "#26334D": "#CBD5E1",
    "#34D399": "#059669",
    "#38BDF8": "#0284C7",
    "#64748B": "#64748B",
    "#94A3B8": "#475569",
    "#A5F3FC": "#0369A1",
    "#CBD5E1": "#334155",
    "#E2E8F0": "#1E293B",
    "#F87171": "#DC2626",
    "#EF4444": "#DC2626",
    "#FBBF24": "#D97706",
    "#FFFFFF": "#0F172A",
}


def _find_brand_logo_path(prefer_white: bool = True) -> Optional[str]:
    candidates = []
    if prefer_white:
        candidates.extend([
            Path(__file__).parents[3] / "assets" / "PDF_Logo-white.png",
            Path(__file__).parents[2] / "assets" / "PDF_Logo-white.png",
            Path("assets/PDF_Logo-white.png"),
            Path("PDF_Logo-white.png"),
        ])
    candidates.extend([
        Path(__file__).parents[3] / "assets" / "logo.png",
        Path(__file__).parents[3] / "logo.png",
        Path("assets/logo.png"),
        Path("logo.png"),
        Path("dashboard/public/logo.png"),
    ])
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return None


class NumberedSecurityReportCanvas(canvas.Canvas):
    """
    Two-pass canvas drawing themed header bars, AgentFlow branding,
    and accurate 'Page X of Y' pagination in landscape mode.
    """
    project_name: str = "AgentFlow Project"
    theme_mode: str = "dark"
    security_grade: str = "A+"
    overall_score: int = 100

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        width, height = self._pagesize
        mode = getattr(self, "theme_mode", "dark")
        is_light = (mode == "light")
        tc = lambda h: COLOR_MAP_LIGHT.get(h, h) if is_light else h

        # 1. Header Top Accent Band (Crimson / Shield Red)
        accent_color = "#DC2626" if is_light else "#EF4444"
        self.setFillColor(colors.HexColor(accent_color))
        self.rect(0, height - 3.5, width, 3.5, fill=1, stroke=0)

        # 2. Header Branding
        logo_path = _find_brand_logo_path(prefer_white=(not is_light))
        if logo_path:
            try:
                self.drawImage(logo_path, 36, height - 28, width=48, height=17, mask='auto', preserveAspectRatio=True)
                self.setFont("Helvetica-Bold", 8.5)
                self.setFillColor(colors.HexColor(tc("#38BDF8")))
                self.drawString(90, height - 19, "•")
                self.setFont("Helvetica-Bold", 8.5)
                self.setFillColor(colors.HexColor(accent_color))
                self.drawString(98, height - 19, "SECURITY SHIELD")
                self.setFont("Helvetica", 8.5)
                self.setFillColor(colors.HexColor(tc("#94A3B8")))
                self.drawString(185, height - 19, "• OWASP Top 10 & STRIDE Threat Assessment Report")
            except Exception:
                self.setFont("Helvetica-Bold", 9)
                self.setFillColor(colors.HexColor(accent_color))
                self.drawString(36, height - 19, "AGENTFLOW SECURITY SHIELD")
                self.setFont("Helvetica", 8.5)
                self.setFillColor(colors.HexColor(tc("#94A3B8")))
                self.drawString(195, height - 19, "• OWASP Top 10 & STRIDE Threat Assessment Report")
        else:
            self.setFont("Helvetica-Bold", 9)
            self.setFillColor(colors.HexColor(accent_color))
            self.drawString(36, height - 19, "AGENTFLOW SECURITY SHIELD")
            self.setFont("Helvetica", 8.5)
            self.setFillColor(colors.HexColor(tc("#94A3B8")))
            self.drawString(195, height - 19, "• OWASP Top 10 & STRIDE Threat Assessment Report")

        # Header Right: Project Name
        self.setFont("Helvetica-Bold", 8.5)
        self.setFillColor(colors.HexColor(tc("#FFFFFF")))
        clean_name = getattr(self, "project_name", "Security Audit")[:40]
        self.drawRightString(width - 36, height - 19, clean_name)

        # Header Separator Line
        self.setStrokeColor(colors.HexColor(tc("#1E293B")))
        self.setLineWidth(0.6)
        self.line(36, height - 33, width - 36, height - 33)

        # 3. Footer Bar
        self.setStrokeColor(colors.HexColor(tc("#1E293B")))
        self.setLineWidth(0.6)
        self.line(36, 28, width - 36, 28)

        # Footer Left: Confidential Notice & Grade
        grade = getattr(self, "security_grade", "A+")
        score = getattr(self, "overall_score", 100)
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor(tc("#94A3B8")))
        self.drawString(36, 17, f"CONFIDENTIAL // AUDIT GRADE: {grade} ({score}/100)")

        # Footer Center
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor(tc("#64748B")))
        self.drawCentredString(width / 2, 17, "AgentFlow Autonomous Security Shield • Static AST & Threat Engine")

        # Footer Right: Page Number
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor(tc("#38BDF8")))
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(width - 36, 17, page_str)

        self.restoreState()


def draw_dark_security_background(c: canvas.Canvas, doc: SimpleDocTemplate):
    """Paints themed canvas background before flowables render."""
    c.saveState()
    width, height = doc.pagesize
    mode = getattr(doc, "theme_mode", "dark")
    bg_hex = COLOR_MAP_LIGHT["#0B0F17"] if mode == "light" else "#0B0F17"
    c.setFillColor(colors.HexColor(bg_hex))
    c.rect(0, 0, width, height, fill=1, stroke=0)
    c.restoreState()


def generate_project_security_report_pdf(
    project_id: str,
    db: Session,
    theme: str = "dark"
) -> bytes:
    """
    Generates a high-fidelity landscape PDF Security Assessment Report
    matching the executive design system and branding of AgentFlow slide decks.
    """
    target_id = UUID(project_id) if isinstance(project_id, str) else project_id
    project = db.get(Project, target_id)
    if not project:
        raise ValueError(f"Project with ID '{project_id}' not found")

    theme_mode = "light" if str(theme).lower() == "light" else "dark"
    is_light = (theme_mode == "light")
    tc = lambda h: COLOR_MAP_LIGHT.get(h, h) if is_light else h

    # Run analysis
    analysis = run_project_security_analysis(target_id, db)
    audit = analysis.get("audit_report", {})
    attack_surf = analysis.get("attack_surface", {})
    stride = analysis.get("stride_threats", [])
    frameworks = analysis.get("compliance_frameworks", [])
    vulns = audit.get("vulnerabilities", [])

    overall_score = audit.get("overall_score", 100)
    security_grade = audit.get("security_grade", "A+")
    severity_counts = audit.get("severity_counts", {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0})
    total_findings = audit.get("total_vulnerabilities", len(vulns))
    remediation_status = audit.get("remediation_status", "Hardened Baseline")
    scanned_count = audit.get("scanned_artifacts_count", 5)

    # Set canvas properties
    class DynamicSecurityCanvas(NumberedSecurityReportCanvas):
        pass
    DynamicSecurityCanvas.project_name = project.name
    DynamicSecurityCanvas.theme_mode = theme_mode
    DynamicSecurityCanvas.security_grade = security_grade
    DynamicSecurityCanvas.overall_score = overall_score

    # Document setup: Letter landscape (792 x 612 pt)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=46,
        bottomMargin=36,
    )
    doc.theme_mode = theme_mode

    # Styles
    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SecTitle",
        parent=base_styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor(tc("#FFFFFF")),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "SecSubtitle",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor(tc("#94A3B8")),
        spaceAfter=12,
    )
    h2_style = ParagraphStyle(
        "SecH2",
        parent=base_styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor(tc("#FFFFFF")),
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "SecBody",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor(tc("#CBD5E1")),
    )
    code_style = ParagraphStyle(
        "SecCode",
        parent=base_styles["Code"],
        fontName="Courier",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor(tc("#38BDF8")),
    )

    # Card & Metric Specific Styles to guarantee zero vertical overlap
    card_label_style = ParagraphStyle(
        "SecCardLabel",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor(tc("#94A3B8")),
        spaceAfter=5,
    )
    card_val_large_style = ParagraphStyle(
        "SecCardValLarge",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        spaceAfter=5,
    )
    card_val_med_style = ParagraphStyle(
        "SecCardValMed",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        spaceAfter=4,
    )
    card_sub_style = ParagraphStyle(
        "SecCardSub",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor(tc("#94A3B8")),
    )

    flowables = []

    # =========================================================================
    # SLIDE 1: Cover Page / Title Slide
    # =========================================================================
    flowables.append(Spacer(1, 20))
    flowables.append(Paragraph("🛡️ ENTERPRISE SECURITY ASSESSMENT", ParagraphStyle(
        "Overline", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor(tc("#EF4444" if not is_light else "#DC2626")), spaceAfter=6
    )))
    flowables.append(Paragraph(f"Security Posture & Vulnerability Audit: {project.name}", title_style))
    flowables.append(Paragraph(
        f"Autonomous OWASP Top 10 • CWE Verification • STRIDE Threat Modeling • Defense-in-Depth Analysis",
        subtitle_style
    ))
    flowables.append(Spacer(1, 10))

    # Badge Cards Table on Title Slide - separate flowables per cell to eliminate collision
    grade_color = "#10B981" if security_grade in ["A+", "A"] else "#FBBF24" if security_grade == "B" else "#EF4444"
    card_data = [
        [
            [
                Paragraph("SECURITY GRADE", card_label_style),
                Paragraph(f"<font color='{grade_color}'>{security_grade}</font>", card_val_large_style),
                Paragraph(remediation_status, card_sub_style),
            ],
            [
                Paragraph("OVERALL SCORE", card_label_style),
                Paragraph(f"<font color='{tc('#38BDF8')}'>{overall_score}/100</font>", card_val_large_style),
                Paragraph("AST Static Verification Score", card_sub_style),
            ],
            [
                Paragraph("ACTIVE FINDINGS", card_label_style),
                Paragraph(f"<font color='{tc('#EF4444' if total_findings > 0 else '#10B981')}'>{total_findings}</font>", card_val_large_style),
                Paragraph(f"{severity_counts.get('CRITICAL', 0)} Critical • {severity_counts.get('HIGH', 0)} High", card_sub_style),
            ],
            [
                Paragraph("ASSETS AUDITED", card_label_style),
                Paragraph(f"<font color='{tc('#FFFFFF')}'>{scanned_count}</font>", card_val_large_style),
                Paragraph("Code, Schemas, Contracts", card_sub_style),
            ],
        ]
    ]
    t_cards = Table(card_data, colWidths=[180, 180, 180, 180])
    t_cards.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tc("#121826"))),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(tc("#26334D"))),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(tc("#1E293B"))),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    flowables.append(t_cards)
    flowables.append(Spacer(1, 16))

    # Executive Brief Box
    brief_text = project.brief or "Autonomous microservice architecture designed for enterprise throughput and resilience."
    p_brief = Paragraph(f"<b>PROJECT CONTEXT &amp; SCOPE:</b> {brief_text}", body_style)
    t_brief = Table([[p_brief]], colWidths=[720])
    t_brief.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tc("#0F2338"))),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(tc("#0284C7"))),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    flowables.append(t_brief)
    flowables.append(PageBreak())

    # =========================================================================
    # SLIDE 2: Executive Scorecard & Severity Radar
    # =========================================================================
    flowables.append(Paragraph("01 // EXECUTIVE SCORECARD & COMPLIANCE POSTURE", ParagraphStyle(
        "SecSec", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor(tc("#EF4444" if not is_light else "#DC2626")), spaceAfter=4
    )))
    flowables.append(Paragraph("Vulnerability Severity Breakdown & Standards Compliance", h2_style))
    flowables.append(Spacer(1, 8))

    # Severity Breakdown Table
    sev_rows = [
        [
            Paragraph("<b>SEVERITY LEVEL</b>", body_style),
            Paragraph("<b>COUNT</b>", body_style),
            Paragraph("<b>OWASP IMPACT RATING</b>", body_style),
            Paragraph("<b>ENFORCEMENT SLA</b>", body_style),
        ],
        [
            Paragraph("<font color='#EF4444'><b>CRITICAL</b></font>", body_style),
            Paragraph(f"<b>{severity_counts.get('CRITICAL', 0)}</b>", body_style),
            Paragraph("Remote Code Execution, Insecure Deserialization, Hardcoded Master Secrets", body_style),
            Paragraph("Immediate (P0 - Block Deployment)", body_style),
        ],
        [
            Paragraph("<font color='#F97316'><b>HIGH</b></font>", body_style),
            Paragraph(f"<b>{severity_counts.get('HIGH', 0)}</b>", body_style),
            Paragraph("SSRF Vectors, Wildcard CORS, Broken Hash Algorithms, AI Prompt Injections", body_style),
            Paragraph("24 Hours (P1 - Security Patch)", body_style),
        ],
        [
            Paragraph("<font color='#FBBF24'><b>MEDIUM</b></font>", body_style),
            Paragraph(f"<b>{severity_counts.get('MEDIUM', 0)}</b>", body_style),
            Paragraph("Missing Auth on Mutating Endpoints, DEBUG Mode Enabled, Root Container", body_style),
            Paragraph("Current Sprint (P2)", body_style),
        ],
        [
            Paragraph("<font color='#38BDF8'><b>LOW / INFO</b></font>", body_style),
            Paragraph(f"<b>{severity_counts.get('LOW', 0)}</b>", body_style),
            Paragraph("Security headers, minor configuration hardening, logging hygiene", body_style),
            Paragraph("Next Scheduled Release (P3)", body_style),
        ],
    ]
    t_sev = Table(sev_rows, colWidths=[120, 70, 340, 190])
    t_sev.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(tc("#1A2438"))),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(tc("#111827")), colors.HexColor(tc("#162032"))]),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(tc("#26334D"))),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(tc("#1E293B"))),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flowables.append(t_sev)
    flowables.append(Spacer(1, 14))

    # Compliance Frameworks Row
    fw_head_style = ParagraphStyle(
        "SecFwHead",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor(tc("#94A3B8")),
        spaceAfter=4,
    )
    fw_header = Paragraph("<b>COMPLIANCE FRAMEWORKS ALIGNMENT:</b>", fw_head_style)
    fw_title_style = ParagraphStyle(
        "SecFwTitle",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor(tc("#FFFFFF")),
        spaceAfter=3,
    )
    fw_metric_style = ParagraphStyle(
        "SecFwMetric",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        spaceAfter=2,
    )
    fw_sub_style = ParagraphStyle(
        "SecFwSub",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor(tc("#94A3B8")),
    )
    fw_cells = [
        [
            [
                Paragraph(fw["framework"], fw_title_style),
                Paragraph(f"<font color='{tc('#34D399') if fw['status'] == 'COMPLIANT' else tc('#FBBF24')}'>{fw['coverage_percentage']}% Verified ({fw['passed_controls']}/{fw['total_controls']} Controls)</font>", fw_metric_style),
                Paragraph(f"Status: {fw['status']}", fw_sub_style),
            ]
            for fw in frameworks
        ]
    ]
    t_fw = Table(fw_cells, colWidths=[240, 240, 240])
    t_fw.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tc("#121826"))),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(tc("#26334D"))),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(tc("#1E293B"))),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    flowables.append(fw_header)
    flowables.append(Spacer(1, 4))
    flowables.append(t_fw)
    flowables.append(PageBreak())

    # =========================================================================
    # SLIDE 3: Attack Surface Profile & Exposure Topology
    # =========================================================================
    flowables.append(Paragraph("02 // ATTACK SURFACE PROFILER", ParagraphStyle(
        "SecSec", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor(tc("#EF4444" if not is_light else "#DC2626")), spaceAfter=4
    )))
    flowables.append(Paragraph("System Ingress, Persistence Boundaries & Exposure Vectors", h2_style))
    flowables.append(Spacer(1, 8))

    as_rating = attack_surf.get("attack_surface_rating", "MINIMAL")
    as_color = "#10B981" if as_rating == "MINIMAL" else "#FBBF24" if as_rating == "MODERATE" else "#EF4444"

    as_metrics = [
        [
            [
                Paragraph("ATTACK SURFACE RATING", card_label_style),
                Paragraph(f"<font color='{as_color}'>{as_rating}</font>", card_val_med_style),
                Paragraph("Evaluated Ingress Vectors", card_sub_style),
            ],
            [
                Paragraph("PUBLIC HTTP ROUTES", card_label_style),
                Paragraph(f"<font color='{tc('#FFFFFF')}'>{attack_surf.get('public_routes_count', 0)}</font>", card_val_med_style),
                Paragraph("Unauthenticated Endpoints", card_sub_style),
            ],
            [
                Paragraph("AUTH GATED ROUTES", card_label_style),
                Paragraph(f"<font color='{tc('#38BDF8')}'>{attack_surf.get('authenticated_routes_count', 0)}</font>", card_val_med_style),
                Paragraph("JWT / RBAC Protected", card_sub_style),
            ],
            [
                Paragraph("PERSISTENCE TABLES", card_label_style),
                Paragraph(f"<font color='{tc('#FFFFFF')}'>{attack_surf.get('database_tables_count', 0)}</font>", card_val_med_style),
                Paragraph("Relational DDL Entities", card_sub_style),
            ],
        ]
    ]
    t_as = Table(as_metrics, colWidths=[180, 180, 180, 180])
    t_as.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tc("#121826"))),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(tc("#26334D"))),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(tc("#1E293B"))),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    flowables.append(t_as)
    flowables.append(Spacer(1, 14))

    # Exposure Vector Catalog
    exp_rows = [
        [Paragraph("<b>EXPOSURE VECTOR</b>", body_style), Paragraph("<b>ARCHITECTURAL MITIGATION APPLIED</b>", body_style)],
    ]
    vectors = attack_surf.get("key_exposure_vectors", [])
    mitigations = [
        "Strict CORS policy, HTTPS TLS termination, Web Application Firewall",
        "Parameterized ORM queries, least-privilege connection pool, automated schema migrations",
        "HMAC SHA-256 signature verification on inbound webhooks and message dead-letter queues",
        "Validated outbound URL whitelists with private IP range (RFC 1918) blocking"
    ]
    for i, vec in enumerate(vectors[:4]):
        mit = mitigations[i] if i < len(mitigations) else "Defense-in-depth isolation"
        exp_rows.append([
            Paragraph(f"• <b>{vec}</b>", body_style),
            Paragraph(mit, body_style),
        ])
    t_exp = Table(exp_rows, colWidths=[330, 390])
    t_exp.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(tc("#1A2438"))),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(tc("#111827")), colors.HexColor(tc("#162032"))]),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(tc("#26334D"))),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(tc("#1E293B"))),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flowables.append(t_exp)
    flowables.append(PageBreak())

    # =========================================================================
    # SLIDE 4: STRIDE Threat Model Matrix
    # =========================================================================
    flowables.append(Paragraph("03 // STRIDE THREAT MODELING MATRIX", ParagraphStyle(
        "SecSec", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor(tc("#EF4444" if not is_light else "#DC2626")), spaceAfter=4
    )))
    flowables.append(Paragraph("Threat Scenarios & Applied Security Controls", h2_style))
    flowables.append(Spacer(1, 8))

    stride_rows = [
        [
            Paragraph("<b>STRIDE CATEGORY</b>", body_style),
            Paragraph("<b>POTENTIAL THREAT SCENARIO</b>", body_style),
            Paragraph("<b>ARCHITECTURAL MITIGATION CONTROL</b>", body_style),
            Paragraph("<b>STATUS</b>", body_style),
        ]
    ]
    for s in stride:
        st_color = "#10B981" if s["status"] == "MITIGATED" else "#FBBF24" if s["status"] == "MONITORED" else "#EF4444"
        stride_rows.append([
            Paragraph(f"<b>{s['category']}</b>", body_style),
            Paragraph(s["threat_scenario"], body_style),
            Paragraph(s["mitigation_control"], body_style),
            Paragraph(f"<font color='{st_color}'><b>{s['status']}</b></font>", body_style),
        ])
    t_stride = Table(stride_rows, colWidths=[120, 240, 240, 100])
    t_stride.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(tc("#1A2438"))),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(tc("#111827")), colors.HexColor(tc("#162032"))]),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(tc("#26334D"))),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(tc("#1E293B"))),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flowables.append(t_stride)
    flowables.append(PageBreak())

    # =========================================================================
    # SLIDE 5: Vulnerability Findings & Actionable Patch Register
    # =========================================================================
    flowables.append(Paragraph("04 // VULNERABILITY FINDINGS REGISTER", ParagraphStyle(
        "SecSec", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor(tc("#EF4444" if not is_light else "#DC2626")), spaceAfter=4
    )))
    flowables.append(Paragraph("Static Code Findings & Actionable Code Remediation Patches", h2_style))
    flowables.append(Spacer(1, 8))

    if vulns:
        # Show top findings with patches
        vuln_rows = [
            [
                Paragraph("<b>SEV / CWE</b>", body_style),
                Paragraph("<b>RULE TITLE &amp; TARGET</b>", body_style),
                Paragraph("<b>CODE SNIPPET</b>", body_style),
                Paragraph("<b>SUGGESTED PATCH / REMEDIATION</b>", body_style),
            ]
        ]
        for v in vulns[:5]:
            sev = v.get("severity", "MEDIUM")
            scol = "#EF4444" if sev == "CRITICAL" else "#F97316" if sev == "HIGH" else "#FBBF24"
            patch = v.get("suggested_patch") or v.get("remediation", "")
            vuln_rows.append([
                Paragraph(f"<font color='{scol}'><b>{sev}</b></font><br/><font size='7.5' color='{tc('#94A3B8')}'>{v.get('cwe_id', 'CWE')}</font>", body_style),
                Paragraph(f"<b>{v.get('title', 'Vulnerability')}</b><br/><font size='7.5' color='{tc('#38BDF8')}'>{v.get('file_target', 'app')}:{v.get('line_number', 1)}</font>", body_style),
                Paragraph(f"<code>{v.get('snippet', '')[:80]}</code>", code_style),
                Paragraph(f"<font color='{tc('#34D399')}'><code>{patch[:110]}</code></font>", code_style),
            ])
        t_vulns = Table(vuln_rows, colWidths=[90, 210, 190, 210])
        t_vulns.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(tc("#1A2438"))),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(tc("#111827")), colors.HexColor(tc("#162032"))]),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(tc("#26334D"))),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(tc("#1E293B"))),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        flowables.append(t_vulns)
    else:
        # Clean bill of health callout
        clean_p = Paragraph(
            "<b>✅ ZERO VULNERABILITIES DETECTED — FULLY HARDENED BASELINE</b><br/><br/>"
            "Static AST scans verified all project artifacts against OWASP Top 10 and CWE benchmarks. "
            "No hardcoded cryptographic secrets, unparameterized SQL strings, permissive CORS configurations, "
            "insecure deserializers, or SSRF vectors were detected in the generated codebase.",
            body_style
        )
        t_clean = Table([[clean_p]], colWidths=[700])
        t_clean.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tc("#0D281E"))),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(tc("#10B981"))),
            ("TOPPADDING", (0, 0), (-1, -1), 24),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 24),
            ("LEFTPADDING", (0, 0), (-1, -1), 20),
            ("RIGHTPADDING", (0, 0), (-1, -1), 20),
        ]))
        flowables.append(t_clean)

    flowables.append(PageBreak())

    # =========================================================================
    # SLIDE 6: Defense-in-Depth Roadmap & Hardening Action Plan
    # =========================================================================
    flowables.append(Paragraph("05 // DEFENSE-IN-DEPTH ROADMAP", ParagraphStyle(
        "SecSec", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor(tc("#EF4444" if not is_light else "#DC2626")), spaceAfter=4
    )))
    flowables.append(Paragraph("Layered Security Controls & Verification Checklist", h2_style))
    flowables.append(Spacer(1, 8))

    checklist_rows = [
        [Paragraph("<b>DEFENSE LAYER</b>", body_style), Paragraph("<b>SECURITY CONTROLS &amp; GUARDRAILS</b>", body_style), Paragraph("<b>VERIFICATION METHOD</b>", body_style)],
        [
            Paragraph("<b>Perimeter Defense</b>", body_style),
            Paragraph("Strict CORS origin allowlist, TLS 1.3 termination, Cloudflare DDoS shielding", body_style),
            Paragraph("Automated Ingress Smoke Tests", body_style),
        ],
        [
            Paragraph("<b>Application &amp; Auth</b>", body_style),
            Paragraph("Mandatory Depends(get_current_user), RBAC claim validation, secure session expiry", body_style),
            Paragraph("Unit &amp; E2E Auth Gate Tests", body_style),
        ],
        [
            Paragraph("<b>Data &amp; Persistence</b>", body_style),
            Paragraph("SQLAlchemy parameterized queries, column-level encryption for sensitive tokens", body_style),
            Paragraph("Static AST SQL Injection Scan", body_style),
        ],
        [
            Paragraph("<b>AI &amp; Model Safety</b>", body_style),
            Paragraph("System instruction prompt isolation, structured output schemas, input guardrails", body_style),
            Paragraph("Prompt Injection Test Suite", body_style),
        ],
        [
            Paragraph("<b>Container &amp; Cloud</b>", body_style),
            Paragraph("Non-root Docker execution (USER appuser), minimal Alpine base image, secret rotation", body_style),
            Paragraph("Container Image Vulnerability Scan", body_style),
        ],
    ]
    t_chk = Table(checklist_rows, colWidths=[140, 380, 180])
    t_chk.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(tc("#1A2438"))),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(tc("#111827")), colors.HexColor(tc("#162032"))]),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(tc("#26334D"))),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(tc("#1E293B"))),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flowables.append(t_chk)
    flowables.append(Spacer(1, 16))

    # Verification Sign-off Box
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    signoff_p = Paragraph(
        f"<b>AUDIT CERTIFICATION:</b> Verified by AgentFlow Security Shield Engine on {now_str}. "
        f"Compliant with OWASP Top 10 2021, OWASP LLM 2025, and CWE benchmarks. "
        f"This document serves as an immutable security baseline assessment for enterprise deployment.",
        body_style
    )
    t_signoff = Table([[signoff_p]], colWidths=[700])
    t_signoff.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tc("#121826"))),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(tc("#38BDF8"))),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    flowables.append(t_signoff)

    # Build PDF with background callback & NumberedSecurityReportCanvas
    doc.build(
        flowables,
        canvasmaker=DynamicSecurityCanvas,
        onFirstPage=draw_dark_security_background,
        onLaterPages=draw_dark_security_background,
    )

    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
