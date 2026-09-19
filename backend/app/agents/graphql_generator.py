import re
from typing import Dict, List, Optional, Tuple
from uuid import UUID
from sqlalchemy.orm import Session

from app.models import Project, ArtifactNode, ArtifactSection
from app.schemas import GraphQLFieldMeta, GraphQLTypeMeta, GraphQLSchemaOut


def _map_sql_type_to_graphql(sql_type: str) -> str:
    norm = sql_type.upper().strip()
    if any(k in norm for k in ["UUID", "SERIAL"]):
        return "ID"
    if any(k in norm for k in ["INT", "BIGINT", "SMALLINT"]):
        return "Int"
    if any(k in norm for k in ["NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "REAL"]):
        return "Float"
    if any(k in norm for k in ["BOOL"]):
        return "Boolean"
    if any(k in norm for k in ["TIME", "DATE"]):
        return "DateTime"
    if any(k in norm for k in ["JSON", "JSONB"]):
        return "JSON"
    return "String"


def _to_pascal_case(name: str) -> str:
    parts = re.split(r"[_\-\s]+", name.strip())
    return "".join(p.capitalize() for p in parts if p) or "Entity"


def _singularize(name: str) -> str:
    lower = name.lower()
    if lower.endswith("ies") and len(name) > 3:
        return name[:-3] + ("Y" if name[-1].isupper() else "y")
    if lower.endswith("ses") and len(name) > 3:
        return name[:-2]
    if lower.endswith("s") and not lower.endswith("ss") and len(name) > 3:
        return name[:-1]
    return name


def _to_camel_case(name: str) -> str:
    pascal = _to_pascal_case(name)
    return pascal[:1].lower() + pascal[1:] if pascal else "entity"


def _extract_tables_from_ddl(ddl: str) -> List[Tuple[str, List[Tuple[str, str, bool]]]]:
    """
    Parses table definitions from SQL DDL into (table_name, [(col_name, col_type, is_not_null)]).
    """
    tables = []
    # Pattern to extract CREATE TABLE statements
    table_pattern = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)\s*\((.*?)\);", re.DOTALL | re.IGNORECASE)
    matches = table_pattern.findall(ddl)

    for table_name, body in matches:
        columns = []
        lines = body.split("\n")
        for line in lines:
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(("PRIMARY KEY", "FOREIGN KEY", "CONSTRAINT", "UNIQUE", "CHECK")):
                continue
            tokens = line.split()
            if len(tokens) >= 2:
                col_name = tokens[0].strip('"').strip('`')
                col_type = tokens[1].upper()
                is_not_null = "NOT NULL" in line.upper() or "PRIMARY KEY" in line.upper()
                columns.append((col_name, col_type, is_not_null))

        if columns:
            tables.append((table_name, columns))

    return tables


def generate_project_graphql(project_id: str, db: Session) -> GraphQLSchemaOut:
    target_id = UUID(project_id) if isinstance(project_id, str) else project_id
    project = db.query(Project).filter(Project.id == target_id).first()
    if not project:
        raise ValueError(f"Project with ID '{project_id}' not found")

    # Extract DDL from DB_SCHEMA node
    nodes = db.query(ArtifactNode).filter(ArtifactNode.project_id == target_id).all()
    ddl_content = ""
    for node in nodes:
        if node.artifact_type == "DB_SCHEMA":
            sections = db.query(ArtifactSection).filter(ArtifactSection.artifact_node_id == node.id).all()
            ddl_content += "\n".join([s.content for s in sections if s.content])

    parsed_tables = _extract_tables_from_ddl(ddl_content)

    # Fallback to standard domain entities if DDL is missing or unparseable
    if not parsed_tables:
        parsed_tables = [
            ("items", [
                ("id", "UUID", True),
                ("title", "VARCHAR", True),
                ("description", "TEXT", False),
                ("status", "VARCHAR", True),
                ("price", "NUMERIC", False),
                ("created_at", "TIMESTAMP", True),
            ]),
            ("users", [
                ("id", "UUID", True),
                ("username", "VARCHAR", True),
                ("email", "VARCHAR", True),
                ("is_active", "BOOLEAN", True),
                ("created_at", "TIMESTAMP", True),
            ])
        ]

    types_meta: List[GraphQLTypeMeta] = []
    sdl_lines: List[str] = [
        f'"""',
        f'GraphQL Schema for {project.name}',
        f'Generated deterministically by AgentFlow GraphQL Generator.',
        f'"""',
        "",
        "scalar DateTime",
        "scalar JSON",
        ""
    ]

    queries_list: List[str] = []
    mutations_list: List[str] = []
    query_examples_list: List[str] = []

    python_types: List[str] = []
    python_queries: List[str] = []
    python_mutations: List[str] = []

    ts_types: List[str] = []
    ts_resolvers_queries: List[str] = []
    ts_resolvers_mutations: List[str] = []

    for table_name, columns in parsed_tables:
        type_name = _singularize(_to_pascal_case(table_name))
        camel_name = _to_camel_case(type_name)
        plural_camel = _to_camel_case(table_name)

        fields_meta: List[GraphQLFieldMeta] = []
        type_fields_sdl = []
        input_fields_sdl = []

        py_fields = []
        ts_fields = []

        for col_name, col_type, is_not_null in columns:
            gql_type = _map_sql_type_to_graphql(col_type)
            bang = "!" if is_not_null else ""
            type_fields_sdl.append(f"  {col_name}: {gql_type}{bang}")

            fields_meta.append(GraphQLFieldMeta(
                name=col_name,
                type_name=gql_type,
                is_nullable=not is_not_null,
                is_list=False,
                description=f"Field {col_name} mapped from {col_type}"
            ))

            # Py type
            py_t = "str"
            if gql_type == "Int": py_t = "int"
            elif gql_type == "Float": py_t = "float"
            elif gql_type == "Boolean": py_t = "bool"
            elif gql_type == "ID": py_t = "strawberry.ID"
            elif gql_type == "DateTime": py_t = "datetime"
            elif gql_type == "JSON": py_t = "dict"

            if not is_not_null:
                py_fields.append(f"    {col_name}: Optional[{py_t}] = None")
            else:
                py_fields.append(f"    {col_name}: {py_t}")

            # TS type
            ts_t = "string"
            if gql_type in ("Int", "Float"): ts_t = "number"
            elif gql_type == "Boolean": ts_t = "boolean"
            elif gql_type == "DateTime": ts_t = "Date"
            elif gql_type == "JSON": ts_t = "Record<string, any>"

            ts_opt = "?" if not is_not_null else ""
            ts_fields.append(f"  {col_name}{ts_opt}: {ts_t};")

            # Input fields exclude auto-generated ID/created_at
            if col_name.lower() not in ["id", "created_at", "updated_at"]:
                input_fields_sdl.append(f"  {col_name}: {gql_type}{bang}")

        types_meta.append(GraphQLTypeMeta(
            name=type_name,
            kind="OBJECT",
            fields=fields_meta,
            description=f"Represents a {type_name} entity in {project.name}"
        ))

        # Build SDL for type
        sdl_lines.append(f'"""Represents {type_name} domain entity."""')
        sdl_lines.append(f"type {type_name} {{")
        sdl_lines.extend(type_fields_sdl)
        sdl_lines.append("}")
        sdl_lines.append("")

        # Build SDL for create input
        create_input_name = f"Create{type_name}Input"
        sdl_lines.append(f"input {create_input_name} {{")
        sdl_lines.extend(input_fields_sdl if input_fields_sdl else type_fields_sdl)
        sdl_lines.append("}")
        sdl_lines.append("")

        # Add Query fields
        queries_list.append(f"  get{type_name}(id: ID!): {type_name}")
        queries_list.append(f"  list{type_name}s(limit: Int = 20, offset: Int = 0): [{type_name}!]!")

        # Add Mutation fields
        mutations_list.append(f"  create{type_name}(input: {create_input_name}!): {type_name}!")
        mutations_list.append(f"  update{type_name}(id: ID!, input: {create_input_name}!): {type_name}!")
        mutations_list.append(f"  delete{type_name}(id: ID!): Boolean!")

        # Query example
        first_cols = [c[0] for c in columns[:4]]
        cols_block = "\n    ".join(first_cols)
        query_examples_list.append(f"""# Query: Fetch list of {type_name}s
query Get{type_name}s {{
  list{type_name}s(limit: 10) {{
    {cols_block}
  }}
}}

# Mutation: Create {type_name}
mutation CreateNew{type_name} {{
  create{type_name}(input: {{}}) {{
    id
    {first_cols[1] if len(first_cols) > 1 else 'id'}
  }}
}}""")

        # Python Strawberry snippet
        python_types.append(f"@strawberry.type\nclass {type_name}:\n" + "\n".join(py_fields) + "\n")
        python_queries.append(f"""    @strawberry.field
    def get_{camel_name}(self, id: strawberry.ID) -> Optional[{type_name}]:
        # Implementation bound to SQLAlchemy session
        return None

    @strawberry.field
    def list_{plural_camel}(self, limit: int = 20, offset: int = 0) -> List[{type_name}]:
        return []""")

        python_mutations.append(f"""    @strawberry.mutation
    def create_{camel_name}(self, input: {create_input_name}) -> {type_name}:
        raise NotImplementedError("Connect to database session")

    @strawberry.mutation
    def delete_{camel_name}(self, id: strawberry.ID) -> bool:
        return True""")

        # TS snippet
        ts_types.append(f"export interface {type_name} {{\n" + "\n".join(ts_fields) + "\n}")
        ts_resolvers_queries.append(f"""    get{type_name}: async (_: any, {{ id }}: {{ id: string }}) => {{
      return await db.{camel_name}.findUnique({{ where: {{ id }} }});
    }},
    list{type_name}s: async (_: any, {{ limit = 20, offset = 0 }}) => {{
      return await db.{camel_name}.findMany({{ take: limit, skip: offset }});
    }},""")

        ts_resolvers_mutations.append(f"""    create{type_name}: async (_: any, {{ input }}: {{ input: any }}) => {{
      return await db.{camel_name}.create({{ data: input }});
    }},
    delete{type_name}: async (_: any, {{ id }}: {{ id: string }}) => {{
      await db.{camel_name}.delete({{ where: {{ id }} }});
      return true;
    }},""")

    # Append Root Query
    sdl_lines.append("type Query {")
    sdl_lines.extend(queries_list)
    sdl_lines.append("}")
    sdl_lines.append("")

    # Append Root Mutation
    sdl_lines.append("type Mutation {")
    sdl_lines.extend(mutations_list)
    sdl_lines.append("}")
    sdl_lines.append("")

    complete_sdl = "\n".join(sdl_lines)
    query_examples = "\n\n".join(query_examples_list)

    # Complete Python Strawberry resolver file
    py_code = f"""\"\"\"
Strawberry GraphQL Schema & Resolvers for {project.name}
Generated by AgentFlow GraphQL Generator.
\"\"\"
import strawberry
from typing import List, Optional
from datetime import datetime


# Types
{"".join(python_types)}

@strawberry.type
class Query:
{chr(10).join(python_queries)}


@strawberry.type
class Mutation:
{chr(10).join(python_mutations)}


schema = strawberry.Schema(query=Query, mutation=Mutation)
"""

    # Complete TypeScript Apollo resolver file
    ts_code = f"""/**
 * TypeScript Apollo Server Resolvers for {project.name}
 * Generated by AgentFlow GraphQL Generator.
 */
import {{ gql }} from 'apollo-server-fastify';

// Entity Interfaces
{"".join(ts_types)}

export const typeDefs = gql`
{complete_sdl}
`;

export const resolvers = {{
  Query: {{
{chr(10).join(ts_resolvers_queries)}
  }},
  Mutation: {{
{chr(10).join(ts_resolvers_mutations)}
  }},
}};
"""

    return GraphQLSchemaOut(
        project_id=project.id,
        project_name=project.name,
        schema_sdl=complete_sdl,
        types=types_meta,
        queries_count=len(queries_list),
        mutations_count=len(mutations_list),
        query_examples=query_examples,
        resolver_code_python=py_code,
        resolver_code_typescript=ts_code
    )
