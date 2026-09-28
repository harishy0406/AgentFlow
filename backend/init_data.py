#!/usr/bin/env python
"""Initialize AgentFlow with test data for PDF generation"""

import sys
from uuid import uuid4

sys.path.append("H:/PROJECTS/Agents/AgentFlow/backend")
from app.database import get_db
from app.models import Project, ArtifactNode, ArtifactSection

db = next(get_db())

# Clean and create project
db.query(Project).filter(Project.name.like("%Test%")).delete()
project = Project(id=uuid4(), name="Test Project", brief="Testing PDF generation")
db.add(project)

# Create required artifacts
artifacts = {
    "PRD": "Product requirements content...",
    "SDD": "System design documentation...",
    "DB_SCHEMA": "CREATE TABLE test (id INT);",
    "API_SPEC": "GET /test - Test endpoint\nPOST /test - Create test",
    "TASKS": "1. Setup database\n2. Create API\n3. Test system"
}

for art_type, content in artifacts.items():
    node = ArtifactNode(id=uuid4(), project_id=project.id, artifact_type=art_type,
                       version=1, status="fresh", quality_signal_score=0.95)
    db.add(node)
    section = ArtifactSection(id=uuid4(), artifact_node_id=node.id, section_key="main",
                            content=content, content_hash=f"hash_{uuid4().hex[:8]}")
    db.add(section)

db.commit()
print(f"✅ Created test project: {project.name} (ID: {project.id})")
print("🚀 Ready for PDF generation!")