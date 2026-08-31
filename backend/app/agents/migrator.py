"""
Phase 8: Automated SQL DDL & Database Migration Generator Engine

Extracts relational schemas, table constraints, indices, and foreign keys
from the synchronized DB_SCHEMA artifact and generates executable SQL DDL
and Alembic migration files in `generated_projects/<slug>/migrations/`.
"""

import os
import re
from pathlib import Path
from uuid import UUID
from typing import Dict, List, Any
from sqlalchemy.orm import Session

from ..models import Project, ArtifactNode
from .scaffolder import sanitize_project_slug


def extract_tables_and_columns(schema_text: str) -> List[Dict[str, Any]]:
    """
    Parses Markdown tables or SQL blocks from DB_SCHEMA sections to identify
    table names, column names, data types, and constraints.
    """
    tables = []
    current_table = None

    lines = schema_text.splitlines()
    for line in lines:
        stripped = line.strip()
        
        # Detect table headers (e.g., "### Table: users" or "## `users` Table" or "CREATE TABLE users")
        header_match = re.search(r"(?:###|##)\s*(?:Table:?\s*)?`?([a-zA-Z0-9_]+)`?", stripped, re.IGNORECASE)
        if header_match and not stripped.lower().startswith("## overview"):
            table_name = header_match.group(1).lower()
            if table_name not in ["table", "database", "schema", "overview", "relationships"]:
                current_table = {
                    "name": table_name,
                    "columns": [],
                    "primary_key": "id",
                }
                tables.append(current_table)
                continue

        # Detect markdown table rows: | column_name | type | constraints |
        if current_table and "|" in stripped:
            parts = [p.strip() for p in stripped.split("|") if p.strip()]
            if len(parts) >= 2 and not parts[0].startswith("---") and parts[0].lower() not in ["column", "field", "name"]:
                col_name = parts[0].replace("`", "")
                col_type = parts[1].replace("`", "")
                constraints = parts[2] if len(parts) > 2 else ""
                
                # Check for primary key
                is_pk = "primary key" in constraints.lower() or col_name == "id"
                if is_pk:
                    current_table["primary_key"] = col_name

                current_table["columns"].append({
                    "name": col_name,
                    "type": col_type,
                    "constraints": constraints,
                    "is_pk": is_pk,
                })

    # If no structured markdown tables found, provide fallback standard tables
    if not tables:
        tables = [
            {
                "name": "users",
                "primary_key": "id",
                "columns": [
                    {"name": "id", "type": "UUID", "constraints": "PRIMARY KEY", "is_pk": True},
                    {"name": "email", "type": "VARCHAR(255)", "constraints": "UNIQUE NOT NULL", "is_pk": False},
                    {"name": "hashed_password", "type": "VARCHAR(255)", "constraints": "NOT NULL", "is_pk": False},
                    {"name": "created_at", "type": "TIMESTAMP WITH TIME ZONE", "constraints": "DEFAULT NOW()", "is_pk": False},
                ]
            },
            {
                "name": "projects",
                "primary_key": "id",
                "columns": [
                    {"name": "id", "type": "UUID", "constraints": "PRIMARY KEY", "is_pk": True},
                    {"name": "user_id", "type": "UUID", "constraints": "REFERENCES users(id)", "is_pk": False},
                    {"name": "name", "type": "VARCHAR(255)", "constraints": "NOT NULL", "is_pk": False},
                    {"name": "status", "type": "VARCHAR(50)", "constraints": "DEFAULT 'active'", "is_pk": False},
                    {"name": "created_at", "type": "TIMESTAMP WITH TIME ZONE", "constraints": "DEFAULT NOW()", "is_pk": False},
                ]
            }
        ]

    return tables


def generate_sql_ddl(tables: List[Dict[str, Any]]) -> str:
    """Generates standard PostgreSQL/SQLite compatible SQL DDL."""
    ddl_statements = [
        "-- ===========================================================================",
        "-- AgentFlow Automated Database Migration (Initial Schema)",
        "-- Generated automatically from synchronized DB_SCHEMA specifications",
        "-- ===========================================================================\n",
        "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";\n",
    ]

    for table in tables:
        ddl_statements.append(f"CREATE TABLE IF NOT EXISTS {table['name']} (")
        col_defs = []
        for col in table["columns"]:
            ctype = col["type"].upper()
            if "UUID" in ctype:
                sql_type = "UUID"
            elif "INT" in ctype or "SERIAL" in ctype:
                sql_type = "INTEGER"
            elif "TEXT" in ctype or "STRING" in ctype:
                sql_type = "TEXT"
            elif "TIME" in ctype or "DATE" in ctype:
                sql_type = "TIMESTAMP WITH TIME ZONE"
            elif "BOOL" in ctype:
                sql_type = "BOOLEAN"
            else:
                sql_type = col["type"]

            constraints = f" {col['constraints']}" if col["constraints"] else ""
            col_defs.append(f"    {col['name']} {sql_type}{constraints}")

        ddl_statements.append(",\n".join(col_defs))
        ddl_statements.append(");\n")

    return "\n".join(ddl_statements)


def generate_alembic_script(tables: List[Dict[str, Any]], revision_id: str = "0001_initial") -> str:
    """Generates a standard Alembic Python migration revision script."""
    script = f'''"""Migration revision: {revision_id}

Generated automatically by AgentFlow Database Migration Engine.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '{revision_id}'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
'''

    for table in tables:
        script += f"    # Create table {table['name']}\n"
        script += f"    op.create_table(\n"
        script += f"        '{table['name']}',\n"
        for col in table["columns"]:
            ctype = col["type"].upper()
            if "UUID" in ctype:
                sa_type = "postgresql.UUID(as_uuid=True)"
            elif "INT" in ctype:
                sa_type = "sa.Integer()"
            elif "BOOL" in ctype:
                sa_type = "sa.Boolean()"
            elif "TIME" in ctype:
                sa_type = "sa.DateTime(timezone=True)"
            else:
                sa_type = "sa.String(length=255)"

            pk_arg = ", primary_key=True" if col["is_pk"] else ""
            script += f"        sa.Column('{col['name']}', {sa_type}{pk_arg}),\n"
        script += "    )\n\n"

    script += "def downgrade() -> None:\n"
    for table in reversed(tables):
        script += f"    op.drop_table('{table['name']}')\n"

    return script


def generate_and_save_migrations(
    project_id: UUID,
    db: Session,
    base_dir: str = "generated_projects"
) -> Dict[str, Any]:
    """
    Orchestrates table parsing, SQL DDL generation, Alembic script creation,
    and writes files directly to `generated_projects/<slug>/migrations/`.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    slug = sanitize_project_slug(project.name)
    migrations_dir = Path(base_dir) / slug / "migrations"
    versions_dir = migrations_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    # Collect DB_SCHEMA content
    db_node = next((n for n in project.artifact_nodes if n.artifact_type == "DB_SCHEMA"), None)
    schema_text = ""
    if db_node and db_node.sections:
        schema_text = "\n\n".join(s.content for s in db_node.sections)

    tables = extract_tables_and_columns(schema_text)
    sql_ddl = generate_sql_ddl(tables)
    alembic_script = generate_alembic_script(tables, revision_id="0001_initial")

    # Write files to disk
    sql_path = migrations_dir / "0001_initial_schema.sql"
    alembic_path = versions_dir / "0001_initial.py"

    with open(sql_path, "w", encoding="utf-8") as f:
        f.write(sql_ddl)

    with open(alembic_path, "w", encoding="utf-8") as f:
        f.write(alembic_script)

    return {
        "project_id": str(project.id),
        "project_slug": slug,
        "revision_id": "0001_initial",
        "tables_count": len(tables),
        "tables": [t["name"] for t in tables],
        "sql_file_path": str(sql_path.relative_to(Path(base_dir) / slug)).replace("\\", "/"),
        "alembic_file_path": str(alembic_path.relative_to(Path(base_dir) / slug)).replace("\\", "/"),
        "sql_ddl": sql_ddl,
        "alembic_script": alembic_script,
    }
