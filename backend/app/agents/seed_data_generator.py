import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from uuid import UUID, uuid4
from sqlalchemy.orm import Session

from app.models import Project, ArtifactNode, ArtifactSection
from app.schemas import SeedEntityData, SeedDataCatalogOut


def _extract_tables_from_ddl(ddl: str) -> List[Tuple[str, List[Tuple[str, str]]]]:
    tables = []
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)\s*\((.*?)\);",
        re.DOTALL | re.IGNORECASE
    )
    matches = pattern.findall(ddl)

    for table_name, body in matches:
        columns = []
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(("PRIMARY KEY", "FOREIGN KEY", "CONSTRAINT", "UNIQUE", "CHECK")):
                continue
            tokens = line.split()
            if len(tokens) >= 2:
                col_name = tokens[0].strip('"').strip('`')
                col_type = tokens[1].upper()
                columns.append((col_name, col_type))

        if columns:
            tables.append((table_name, columns))

    return tables


def _generate_synthetic_value(col_name: str, col_type: str, index: int) -> Any:
    norm_col = col_name.lower()
    norm_type = col_type.upper()

    if "id" in norm_col or "uuid" in norm_type:
        return f"00000000-0000-0000-0000-00000000000{index+1}"[-36:]
    if "email" in norm_col:
        return f"user{index+1}@example.com"
    if any(k in norm_col for k in ["username", "user_name"]):
        return f"user_{index+1}"
    if any(k in norm_col for k in ["name", "title"]):
        return f"Sample {col_name.capitalize()} {index+1}"
    if any(k in norm_col for k in ["status", "state"]):
        return ["active", "pending", "completed", "approved"][index % 4]
    if any(k in norm_col for k in ["amount", "price", "balance", "cost", "total"]):
        return round(29.99 + (index * 15.5), 2)
    if "currency" in norm_col:
        return ["USD", "EUR", "GBP"][index % 3]
    if any(k in norm_col for k in ["is_", "has_", "active", "enabled", "frozen", "bool"]):
        return index % 2 == 0
    if any(k in norm_type for k in ["INT", "SERIAL"]):
        return (index + 1) * 10
    if any(k in norm_type for k in ["NUMERIC", "DECIMAL", "FLOAT", "DOUBLE"]):
        return round(10.0 + index * 4.25, 2)
    if any(k in norm_type for k in ["TIME", "DATE"]):
        return f"2026-09-20 0{index+1}:00:00"
    if any(k in norm_type for k in ["JSON", "JSONB"]):
        return {"env": "staging", "version": index + 1, "metadata": {"source": "seed_data"}}

    return f"sample_{col_name}_{index+1}"


def generate_project_seed_data(project_id: str, db: Session, count_per_table: int = 5) -> SeedDataCatalogOut:
    target_id = UUID(project_id) if isinstance(project_id, str) else project_id
    project = db.query(Project).filter(Project.id == target_id).first()
    if not project:
        raise ValueError(f"Project with ID '{project_id}' not found")

    # Extract DDL
    nodes = db.query(ArtifactNode).filter(ArtifactNode.project_id == target_id).all()
    ddl_content = ""
    for node in nodes:
        if node.artifact_type == "DB_SCHEMA":
            sections = db.query(ArtifactSection).filter(ArtifactSection.artifact_node_id == node.id).all()
            ddl_content += "\n".join([s.content for s in sections if s.content])

    parsed_tables = _extract_tables_from_ddl(ddl_content)

    # Fallback to standard core tables
    if not parsed_tables:
        parsed_tables = [
            ("users", [
                ("id", "UUID"),
                ("username", "VARCHAR"),
                ("email", "VARCHAR"),
                ("is_active", "BOOLEAN"),
                ("created_at", "TIMESTAMP"),
            ]),
            ("items", [
                ("id", "UUID"),
                ("title", "VARCHAR"),
                ("price", "NUMERIC"),
                ("status", "VARCHAR"),
                ("created_at", "TIMESTAMP"),
            ])
        ]

    entities_out: List[SeedEntityData] = []
    fixture_dict: Dict[str, List[Dict[str, Any]]] = {}
    sql_statements: List[str] = [
        f"-- Synthetic Seed Data Fixtures for {project.name}",
        f"-- Generated deterministically on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "BEGIN;\n"
    ]

    python_factories: List[str] = []
    ts_seeders: List[str] = []

    total_records = 0

    for table_name, columns in parsed_tables:
        records = []
        for i in range(count_per_table):
            row = {}
            for col_name, col_type in columns:
                row[col_name] = _generate_synthetic_value(col_name, col_type, i)
            records.append(row)

        fixture_dict[table_name] = records
        total_records += len(records)
        entities_out.append(SeedEntityData(
            table_name=table_name,
            row_count=len(records),
            sample_records=records
        ))

        # Build SQL INSERT statement
        col_names_str = ", ".join(c[0] for c in columns)
        val_rows = []
        for r in records:
            vals = []
            for c_name, _ in columns:
                v = r[c_name]
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, bool):
                    vals.append("TRUE" if v else "FALSE")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                elif isinstance(v, dict):
                    escaped_json = json.dumps(v).replace("'", "''")
                    vals.append(f"'{escaped_json}'::jsonb")
                else:
                    escaped_str = str(v).replace("'", "''")
                    vals.append(f"'{escaped_str}'")
            val_rows.append(f"  ({', '.join(vals)})")

        sql_statements.append(f"-- Seeding {table_name}")
        sql_statements.append(f"INSERT INTO {table_name} ({col_names_str}) VALUES")
        sql_statements.append(",\n".join(val_rows) + ";\n")

        # Python FactoryBoy snippet
        class_name = "".join(p.capitalize() for p in table_name.split("_"))
        py_fields = []
        for c_name, c_type in columns:
            if "id" in c_name.lower():
                py_fields.append(f"    {c_name} = factory.Faker('uuid4')")
            elif "email" in c_name.lower():
                py_fields.append(f"    {c_name} = factory.Faker('email')")
            elif any(k in c_name.lower() for k in ["name", "title"]):
                py_fields.append(f"    {c_name} = factory.Faker('catch_phrase')")
            elif any(k in c_name.lower() for k in ["price", "amount"]):
                py_fields.append(f"    {c_name} = factory.Faker('pydecimal', left_digits=4, right_digits=2, positive=True)")
            elif "bool" in c_type.lower() or "is_" in c_name.lower():
                py_fields.append(f"    {c_name} = factory.Faker('boolean')")
            elif "date" in c_type.lower() or "time" in c_type.lower():
                py_fields.append(f"    {c_name} = factory.LazyFunction(datetime.utcnow)")
            else:
                py_fields.append(f"    {c_name} = factory.Faker('word')")

        python_factories.append(f"class {class_name}Factory(factory.alchemy.SQLAlchemyModelFactory):\n    class Meta:\n        model = models.{class_name}\n        sqlalchemy_session = db.session\n\n" + "\n".join(py_fields) + "\n")

        # TypeScript Prisma / Knex Seeder snippet
        ts_seeders.append(f"""  // Seed {table_name}
  for (const item of seedData.{table_name}) {{
    await prisma.{table_name}.upsert({{
      where: {{ id: item.id }},
      update: {{}},
      create: item,
    }});
  }}""")

    sql_statements.append("COMMIT;")
    sql_script = "\n".join(sql_statements)
    json_fixture = json.dumps(fixture_dict, indent=2)

    py_factory_code = f"""\"\"\"
Pytest Test Factories for {project.name}
Generated by AgentFlow Seed Data Engine using FactoryBoy & Faker
\"\"\"
import factory
from datetime import datetime
from app import models, db


{chr(10).join(python_factories)}
"""

    ts_seed_code = f"""/**
 * Database Seeder for {project.name}
 * Generated by AgentFlow Seed Data Engine
 */
import {{ PrismaClient }} from '@prisma/client';
import seedData from './seeds.json';

const prisma = new PrismaClient();

async function main() {{
  console.log('🌱 Starting database seeding for {project.name}...');

{chr(10).join(ts_seeders)}

  console.log('✅ Seeding completed successfully!');
}}

main()
  .catch((e) => {{
    console.error('❌ Seeding failed:', e);
    process.exit(1);
  }})
  .finally(async () => {{
    await prisma.$disconnect();
  }});
"""

    return SeedDataCatalogOut(
        project_id=project.id,
        project_name=project.name,
        total_records=total_records,
        entities=entities_out,
        sql_script=sql_script,
        json_fixture=json_fixture,
        python_factory_code=py_factory_code,
        typescript_seed_code=ts_seed_code
    )
