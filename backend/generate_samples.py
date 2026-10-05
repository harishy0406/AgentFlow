import os
import sys
from pathlib import Path
from uuid import uuid4

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import get_db, engine, Base
from app.models import Project, ArtifactNode, ArtifactSection
from app.reports.pdf_presentation import generate_project_presentation_pdf
from app.agents.template_seeds import get_template_definition

import fitz  # PyMuPDF

def main():
    Base.metadata.create_all(bind=engine)
    db = next(get_db())

    output_dir = Path(__file__).resolve().parent.parent / "sample_reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = [
        {
            "name": "Enterprise E-Commerce Platform",
            "brief": "A scalable multi-vendor e-commerce marketplace featuring cart reservation, payment webhooks, vendor catalog management, and distributed order processing.",
            "template_key": "ecommerce_marketplace",
            "pdf_name": "ecommerce_platform_architectural_deck.pdf",
            "img_prefix": "ecommerce_slide"
        },
        {
            "name": "Autonomous AI Code Reviewer",
            "brief": "An automated AI code review platform that analyzes git pull requests, evaluates AST syntax, checks OWASP compliance, and detects architectural drift.",
            "template_key": "ai_code_reviewer",
            "pdf_name": "ai_code_reviewer_architectural_deck.pdf",
            "img_prefix": "ai_reviewer_slide"
        }
    ]

    for item in samples:
        print(f"\n--- Generating: {item['name']} ---")
        t_def = get_template_definition(item["template_key"])
        if not t_def:
            print(f"Warning: Template {item['template_key']} not found directly, will use fallback.")

        # Check if project already exists
        project = db.query(Project).filter(Project.name == item["name"]).first()
        if not project:
            project = Project(
                id=uuid4(),
                name=item["name"],
                brief=item["brief"]
            )
            db.add(project)
            db.commit()
            db.refresh(project)

        # Seed artifacts if not present
        if t_def and not project.artifact_nodes:
            artifacts_data = t_def.get("artifacts", {})
            for art_type, art_val in artifacts_data.items():
                node = ArtifactNode(
                    id=uuid4(),
                    project_id=project.id,
                    artifact_type=art_type,
                    version=1,
                    status="fresh"
                )
                db.add(node)
                db.commit()
                db.refresh(node)

                # Add section
                content_str = ""
                if isinstance(art_val, dict):
                    content_str = "\n\n".join(str(v) for v in art_val.values() if isinstance(v, str))
                elif isinstance(art_val, str):
                    content_str = art_val

                if content_str:
                    sec = ArtifactSection(
                        id=uuid4(),
                        artifact_node_id=node.id,
                        section_key="main",
                        content=content_str,
                        content_hash="hash_" + str(uuid4())[:8]
                    )
                    db.add(sec)
            db.commit()
            db.refresh(project)

        pdf_bytes = generate_project_presentation_pdf(str(project.id), db)
        pdf_path = output_dir / item["pdf_name"]
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"Generated PDF: {pdf_path} ({len(pdf_bytes):,} bytes)")

        # Render slides to PNG
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        print(f"Total slides: {len(doc)}")
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=150)
            img_path = output_dir / f"{item['img_prefix']}_{page_idx + 1}.png"
            pix.save(str(img_path))
        print(f"Exported {len(doc)} slide images for {item['name']}")

    print("\nAll sample PDFs and slide images successfully generated!")

if __name__ == "__main__":
    main()
