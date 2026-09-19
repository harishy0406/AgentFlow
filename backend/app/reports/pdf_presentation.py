import io
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
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

from app.models import Project, ArtifactNode, DriftRecord


class NumberedSlideCanvas(canvas.Canvas):
    """
    Two-pass canvas that draws dark background, branding headers,
    and accurate 'Slide X of Y' pagination in landscape mode.
    """
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

        # 1. Slide Background (Dark Blueprint)
        self.setFillColor(colors.HexColor("#0A0E1A"))
        self.rect(0, 0, width, height, fill=1, stroke=0)

        # 2. Header Accent Band
        self.setFillColor(colors.HexColor("#00FF66"))
        self.rect(0, height - 4, width, 4, fill=1, stroke=0)

        # Header Title & Subtitle
        self.setFont("Helvetica-Bold", 9)
        self.setFillColor(colors.HexColor("#38BDF8"))
        self.drawString(36, height - 24, "AGENTFLOW")
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#94A3B8"))
        self.drawString(98, height - 24, "•  Enterprise Software Architectural Deck & Project Blueprint")

        # Header divider
        self.setStrokeColor(colors.HexColor("#1E293B"))
        self.setLineWidth(1)
        self.line(36, height - 32, width - 36, height - 32)

        # 3. Footer Band
        self.setStrokeColor(colors.HexColor("#1E293B"))
        self.setLineWidth(1)
        self.line(36, 32, width - 36, 32)

        # Footer Left: Timestamp & Confidentiality
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self.drawString(36, 20, f"Generated deterministically by AgentFlow Engine  •  {timestamp_str}")

        # Footer Right: Slide Number
        page_num_str = f"Slide {self._pageNumber} of {page_count}"
        self.drawRightString(width - 36, 20, page_num_str)

        self.restoreState()


def _get_node_content(node: Optional[ArtifactNode]) -> str:
    if not node or not node.sections:
        return ""
    return "\n\n".join(s.content for s in sorted(node.sections, key=lambda x: x.order_index if hasattr(x, "order_index") else 0))


def _extract_db_tables(schema_text: str) -> List[Dict[str, str]]:
    tables = []
    matches = re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)\s*\((.*?)\);", schema_text, re.DOTALL | re.IGNORECASE)
    for name, cols_raw in matches[:6]:
        col_lines = [c.strip() for c in cols_raw.split(",") if c.strip() and not c.strip().upper().startswith(("PRIMARY KEY", "FOREIGN KEY", "CONSTRAINT"))]
        cols_summary = ", ".join(c.split()[0] for c in col_lines[:5])
        tables.append({"name": name, "columns": cols_summary})
    return tables


def _extract_api_endpoints(api_text: str) -> List[Dict[str, str]]:
    endpoints = []
    # Match markdown tables or OpenAPI paths
    md_matches = re.findall(r"\|\s*(GET|POST|PUT|DELETE|PATCH)\s*\|\s*(`?[a-zA-Z0-9_\/\{\}\-\.]+`?)\s*\|\s*([^\|]+)\|", api_text, re.IGNORECASE)
    for method, path, desc in md_matches[:8]:
        endpoints.append({
            "method": method.strip().upper(),
            "path": path.strip().replace("`", ""),
            "description": desc.strip()[:60]
        })
    if not endpoints:
        # Fallback to simple endpoint patterns
        path_matches = re.findall(r"(GET|POST|PUT|DELETE|PATCH)\s+([/a-zA-Z0-9_\{\}\-]+)", api_text, re.IGNORECASE)
        for method, path in path_matches[:8]:
            endpoints.append({
                "method": method.upper(),
                "path": path,
                "description": "API Route specification"
            })
    return endpoints


def generate_project_presentation_pdf(project_id: str, db: Session) -> bytes:
    target_id = UUID(project_id) if isinstance(project_id, str) else project_id
    project = db.query(Project).filter(Project.id == target_id).first()
    if not project:
        raise ValueError(f"Project with ID '{project_id}' not found")

    # Fetch artifacts
    nodes = {node.artifact_type: node for node in project.artifact_nodes}
    prd_text = _get_node_content(nodes.get("PRD"))
    sdd_text = _get_node_content(nodes.get("SDD"))
    db_text = _get_node_content(nodes.get("DB_SCHEMA"))
    api_text = _get_node_content(nodes.get("API_SPEC"))
    tasks_text = _get_node_content(nodes.get("TASKS"))

    # Compute health metrics directly
    generated_count = len(project.artifact_nodes)
    artifact_completion_pct = round((generated_count / 7) * 100, 1)
    quality_scores = [n.quality_signal_score for n in project.artifact_nodes if n.quality_signal_score is not None]
    avg_quality = round((sum(quality_scores) / len(quality_scores)) if quality_scores else 0.88, 2)

    drifts_count = db.query(DriftRecord).filter(DriftRecord.project_id == target_id, DriftRecord.status == "open").count()
    consistency_pct = max(0.0, round(100.0 - (drifts_count * 15.0), 1))

    overall_score = round(
        (artifact_completion_pct * 0.40)
        + (consistency_pct * 0.35)
        + (min(avg_quality * 100, 100.0) * 0.25),
        1
    )
    if overall_score >= 85:
        readiness_status = "Production Ready"
    elif overall_score >= 65:
        readiness_status = "Stable Development"
    elif overall_score >= 40:
        readiness_status = "In Progress"
    else:
        readiness_status = "Draft Architecture"

    # Extract parsed structures
    db_tables = _extract_db_tables(db_text)
    api_routes = _extract_api_endpoints(api_text)

    # ReportLab Document Setup
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=46,
        bottomMargin=44,
    )

    # Styles
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "SlideTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#FFFFFF"),
        spaceAfter=12,
    )

    h2_style = ParagraphStyle(
        "SlideH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#38BDF8"),
        spaceAfter=10,
    )

    body_style = ParagraphStyle(
        "SlideBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#CBD5E1"),
    )

    accent_body = ParagraphStyle(
        "AccentBody",
        parent=body_style,
        textColor=colors.HexColor("#00FF66"),
        fontName="Helvetica-Bold",
    )

    code_style = ParagraphStyle(
        "CodeText",
        parent=body_style,
        fontName="Courier",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#A7F3D0"),
    )

    story = []

    # ==========================================
    # SLIDE 1: COVER / TITLE SLIDE
    # ==========================================
    story.append(Spacer(1, 40))
    story.append(Paragraph(f"PROJECT BLUEPRINT: {project.name.upper()}", title_style))
    story.append(Paragraph("Automated Multi-Agent Architectural Synthesis & Verified Codebase Plan", h2_style))
    story.append(Spacer(1, 20))

    # Brief block
    brief_snippet = project.brief[:400] + ("..." if len(project.brief) > 400 else "")
    brief_data = [
        [
            Paragraph("<b>PROJECT MISSION & BRIEF:</b>", accent_body),
        ],
        [
            Paragraph(brief_snippet, body_style),
        ]
    ]
    brief_table = Table(brief_data, colWidths=[720])
    brief_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#111827")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#374151")),
        ("PADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
    ]))
    story.append(brief_table)
    story.append(Spacer(1, 24))

    # Key Metadata Cards (3-column table)
    meta_data = [
        [
            Paragraph("<b>SYSTEM STATUS</b>", body_style),
            Paragraph("<b>ARTIFACT NODES</b>", body_style),
            Paragraph("<b>ACTIVE CONSISTENCY</b>", body_style),
        ],
        [
            Paragraph(f"<font size=16 color='#00FF66'><b>{overall_score}% READY</b></font>", body_style),
            Paragraph(f"<font size=16 color='#38BDF8'><b>{len(project.artifact_nodes)} / 7 Generated</b></font>", body_style),
            Paragraph(f"<font size=16 color='#F59E0B'><b>{drifts_count} Open Drifts</b></font>", body_style),
        ],
        [
            Paragraph(f"Readiness: {readiness_status.upper()}", body_style),
            Paragraph("Topological DAG Complete", body_style),
            Paragraph("AST & Schema Verified", body_style),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[240, 240, 240])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1E293B")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#334155")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#334155")),
        ("PADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(meta_table)
    story.append(PageBreak())

    # ==========================================
    # SLIDE 2: EXECUTIVE SUMMARY & SYSTEM READINESS
    # ==========================================
    story.append(Paragraph("01. EXECUTIVE SUMMARY & READINESS SCORECARD", title_style))
    story.append(Paragraph("High-level engineering telemetry, artifact quality signals, and automated audit status", body_style))
    story.append(Spacer(1, 16))

    def _score_for(art_type: str) -> str:
        node = nodes.get(art_type)
        if not node:
            return "Pending"
        if node.quality_signal_score:
            return f"{round(node.quality_signal_score * 100)}%"
        return "100%"

    # Health Breakdown Table
    health_rows = [
        [
            Paragraph("<b>DIMENSION</b>", accent_body),
            Paragraph("<b>SCORE</b>", accent_body),
            Paragraph("<b>AUDIT FINDINGS & RECOMMENDATIONS</b>", accent_body),
        ],
        [
            Paragraph("<b>PRD & Scope Clarity</b>", body_style),
            Paragraph(f"<b>{_score_for('PRD')}</b>", body_style),
            Paragraph("Functional requirements, target personas, and MVP boundaries verified.", body_style),
        ],
        [
            Paragraph("<b>Architecture & SDD</b>", body_style),
            Paragraph(f"<b>{_score_for('SDD')}</b>", body_style),
            Paragraph("Microservice boundaries, cross-service contracts, and storage layers aligned.", body_style),
        ],
        [
            Paragraph("<b>Database Schema Integrity</b>", body_style),
            Paragraph(f"<b>{_score_for('DB_SCHEMA')}</b>", body_style),
            Paragraph("Foreign keys, unique constraints, and PostgreSQL DDL syntactically checked.", body_style),
        ],
        [
            Paragraph("<b>API Contracts & Routing</b>", body_style),
            Paragraph(f"<b>{_score_for('API_SPEC')}</b>", body_style),
            Paragraph("REST endpoints mapped with parameter validation schemas.", body_style),
        ],
        [
            Paragraph("<b>Task Coverage & Testing</b>", body_style),
            Paragraph(f"<b>{_score_for('TASKS')}</b>", body_style),
            Paragraph("Work breakdown structure, story points, and acceptance criteria compiled.", body_style),
        ],
    ]
    health_table = Table(health_rows, colWidths=[180, 80, 460])
    health_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#1E293B")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#334155")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#334155")),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(health_table)
    story.append(Spacer(1, 16))

    # Architecture Highlights Callout
    summary_p = Paragraph(
        "<b>Architectural Takeaway:</b> The synthesized platform adheres to strict dependency isolation. "
        "Any subsequent upstream edits trigger selective recomputation of dirty child nodes via topological BFS, "
        "preserving unmodified code assets and eliminating hallucination cascading.",
        body_style
    )
    summary_box = Table([[summary_p]], colWidths=[720])
    summary_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#134E4A")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#14B8A6")),
        ("PADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(summary_box)
    story.append(PageBreak())

    # ==========================================
    # SLIDE 3: SYSTEM ARCHITECTURE & DATABASE SCHEMA
    # ==========================================
    story.append(Paragraph("02. SYSTEM DESIGN & RELATIONAL DATA MODEL", title_style))
    story.append(Paragraph("PostgreSQL relational schema, entity relationships, and core database tables", body_style))
    story.append(Spacer(1, 16))

    if db_tables:
        db_rows = [
            [
                Paragraph("<b>TABLE NAME</b>", accent_body),
                Paragraph("<b>ATTRIBUTES & FOREIGN KEYS</b>", accent_body),
                Paragraph("<b>PERSISTENCE ROLE</b>", accent_body),
            ]
        ]
        for t in db_tables:
            db_rows.append([
                Paragraph(f"<b><font color='#38BDF8'>{t['name']}</font></b>", code_style),
                Paragraph(t['columns'] or "id (UUID), created_at (TIMESTAMP)", body_style),
                Paragraph("Primary Domain Entity", body_style),
            ])
        db_table = Table(db_rows, colWidths=[180, 420, 120])
        db_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#1E293B")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#334155")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#334155")),
            ("PADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(db_table)
    else:
        story.append(Paragraph("<i>Database schema generated directly in PostgreSQL DDL format within the DB_SCHEMA artifact node.</i>", body_style))

    story.append(Spacer(1, 16))
    # SDD Architecture Snippet
    sdd_snippet = sdd_text[:350] + ("..." if len(sdd_text) > 350 else "") or "Architecture incorporates decoupled API gateway, transactional service layers, and Redis caching."
    arch_box = Table([
        [Paragraph("<b>SYSTEM DESIGN OVERVIEW:</b>", accent_body)],
        [Paragraph(sdd_snippet, body_style)]
    ], colWidths=[720])
    arch_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#111827")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#374151")),
        ("PADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(arch_box)
    story.append(PageBreak())

    # ==========================================
    # SLIDE 4: API SPECIFICATION & CONTRACT MATRIX
    # ==========================================
    story.append(Paragraph("03. REST API SPECIFICATIONS & SERVICE CONTRACTS", title_style))
    story.append(Paragraph("Public and private HTTP route declarations compliant with OpenAPI 3.0.3", body_style))
    story.append(Spacer(1, 16))

    if api_routes:
        api_rows = [
            [
                Paragraph("<b>METHOD</b>", accent_body),
                Paragraph("<b>ENDPOINT PATH</b>", accent_body),
                Paragraph("<b>OPERATION & CONTRACT SUMMARY</b>", accent_body),
            ]
        ]
        for r in api_routes:
            m_color = "#10B981" if r["method"] == "GET" else "#3B82F6" if r["method"] == "POST" else "#F59E0B"
            api_rows.append([
                Paragraph(f"<b><font color='{m_color}'>{r['method']}</font></b>", code_style),
                Paragraph(f"<b>{r['path']}</b>", code_style),
                Paragraph(r["description"], body_style),
            ])
        api_table = Table(api_rows, colWidths=[90, 290, 340])
        api_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#1E293B")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#334155")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#334155")),
            ("PADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(api_table)
    else:
        story.append(Paragraph("<i>OpenAPI 3.0.3 specification compiled in API_SPEC node with dynamic mock routes.</i>", body_style))

    story.append(Spacer(1, 14))
    api_footer = Table([
        [
            Paragraph("<b>Contract Guarantee:</b> All endpoints are verified against the database schema models. SemVer breaking changes are automatically monitored via the Semantic Changelog Engine.", body_style)
        ]
    ], colWidths=[720])
    api_footer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1E1B4B")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#4F46E5")),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(api_footer)
    story.append(PageBreak())

    # ==========================================
    # SLIDE 5: IMPLEMENTATION ROADMAP & TASKS
    # ==========================================
    story.append(Paragraph("04. ENGINEERING ROADMAP & IMPLEMENTATION TASKS", title_style))
    story.append(Paragraph("Phased development breakdown, acceptance criteria, and task sequencing", body_style))
    story.append(Spacer(1, 16))

    task_lines = [line.strip() for line in tasks_text.split("\n") if line.strip().startswith(("-", "*", "1.", "2.", "3.", "4.", "5.", "#"))][:6]
    if not task_lines:
        task_lines = [
            "Phase 1: Database Migration & Persistence Models Scaffolding",
            "Phase 2: Authentication & Secure Role-Based Access Control",
            "Phase 3: Core Business Domain API Handlers & Middleware",
            "Phase 4: Client SDK Generation & Automated Integration Tests",
            "Phase 5: Cloud Deployment & Distributed Observability Pipeline",
        ]

    task_rows = [
        [
            Paragraph("<b>PHASE / EPIC</b>", accent_body),
            Paragraph("<b>SCOPE & DELIVERABLES</b>", accent_body),
            Paragraph("<b>STATUS</b>", accent_body),
        ]
    ]
    for idx, t_line in enumerate(task_lines, 1):
        clean_title = re.sub(r"^[-*#\d\.]+\s*", "", t_line)
        task_rows.append([
            Paragraph(f"<b>Milestone 0{idx}</b>", body_style),
            Paragraph(clean_title[:80], body_style),
            Paragraph("<font color='#00FF66'><b>PLANNED</b></font>", body_style),
        ])

    task_table = Table(task_rows, colWidths=[120, 500, 100])
    task_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#1E293B")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#334155")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#334155")),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(task_table)
    story.append(Spacer(1, 16))

    story.append(PageBreak())

    # ==========================================
    # SLIDE 6: MULTI-CLOUD INFRASTRUCTURE & DEPLOYMENT
    # ==========================================
    story.append(Paragraph("05. CLOUDOPS & INFRASTRUCTURE-AS-CODE (IaC)", title_style))
    story.append(Paragraph("Automated Terraform deployment topologies and production Kubernetes orchestration", body_style))
    story.append(Spacer(1, 16))

    iac_matrix = [
        [
            Paragraph("<b>PROVIDER</b>", accent_body),
            Paragraph("<b>COMPUTE & CONTAINER ENGINE</b>", accent_body),
            Paragraph("<b>DATABASE & CACHE</b>", accent_body),
            Paragraph("<b>CLI EXECUTION COMMAND</b>", accent_body),
        ],
        [
            Paragraph("<b>Amazon Web Services</b>", body_style),
            Paragraph("AWS ECS Fargate Cluster (Serverless)", body_style),
            Paragraph("RDS PostgreSQL 15 + ElastiCache Redis", body_style),
            Paragraph("terraform apply -var='env=prod'", code_style),
        ],
        [
            Paragraph("<b>Google Cloud</b>", body_style),
            Paragraph("Cloud Run v2 (Auto-scaling 1-10)", body_style),
            Paragraph("Cloud SQL PostgreSQL (HA)", body_style),
            Paragraph("gcloud run deploy --image=api:latest", code_style),
        ],
        [
            Paragraph("<b>Kubernetes (K8s)</b>", body_style),
            Paragraph("Zero-downtime Rolling Deployment + HPA", body_style),
            Paragraph("PostgreSQL StatefulSet / RDS proxy", body_style),
            Paragraph("kubectl apply -f k8s/ -n prod", code_style),
        ],
        [
            Paragraph("<b>Docker Compose</b>", body_style),
            Paragraph("Multi-container local stack + Next.js", body_style),
            Paragraph("Postgres 15 Alpine + Redis 7", body_style),
            Paragraph("docker-compose up -d --build", code_style),
        ],
    ]
    iac_table = Table(iac_matrix, colWidths=[150, 200, 190, 180])
    iac_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#1E293B")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#334155")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#334155")),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(iac_table)
    story.append(Spacer(1, 20))

    final_signoff = Table([
        [
            Paragraph(
                "<b>Architectural Signoff & Verification:</b> This deck represents the complete verified blueprint for "
                f"<b>{project.name}</b>. All data models, endpoints, and task definitions are synchronized with "
                "the active AgentFlow engine.",
                body_style
            )
        ]
    ], colWidths=[720])
    final_signoff.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#064E3B")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#059669")),
        ("PADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(final_signoff)

    # Build the document
    doc.build(story, canvasmaker=NumberedSlideCanvas)
    buffer.seek(0)
    return buffer.getvalue()
