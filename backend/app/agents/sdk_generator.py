"""
Phase 8+: Multi-Language Client SDK Generator Engine

Automatically generates production-grade, type-safe client SDK libraries
in TypeScript, Python, and cURL/CLI from project API contracts and DB schemas.
"""

import re
from uuid import UUID
from typing import Dict, Any, List, Union, Optional
from sqlalchemy.orm import Session

from ..models import Project, ArtifactNode
from .scaffolder import sanitize_project_slug
from .openapi_generator import _extract_routes, _extract_schemas


def _to_pascal_case(text: str) -> str:
    """Converts a snake_case or slug string into PascalCase."""
    clean = re.sub(r"[^a-zA-Z0-9]", " ", text)
    return "".join(word.capitalize() for word in clean.split())


def _to_camel_case(text: str) -> str:
    """Converts a string to camelCase."""
    pascal = _to_pascal_case(text)
    return pascal[0].lower() + pascal[1:] if pascal else "resource"


def _to_snake_case(text: str) -> str:
    """Converts string to snake_case."""
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', text)
    s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", s2)
    return re.sub(r'_+', '_', clean).strip('_').lower()



def _generate_method_name(method: str, path: str) -> str:
    """Generates an intuitive method name like listUsers, getProductById, createOrder."""
    clean_parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]
    resource = clean_parts[-1] if clean_parts else "item"
    has_id = any(p.startswith("{") for p in path.split("/"))

    m = method.upper()
    if m == "GET":
        return f"get{_to_pascal_case(resource)}" if has_id else f"list{_to_pascal_case(resource)}"
    elif m == "POST":
        return f"create{_to_pascal_case(resource)}"
    elif m in ["PUT", "PATCH"]:
        return f"update{_to_pascal_case(resource)}"
    elif m == "DELETE":
        return f"delete{_to_pascal_case(resource)}"
    return f"{m.lower()}{_to_pascal_case(resource)}"


def _generate_typescript_sdk(
    project_slug: str,
    routes: List[Dict[str, Any]],
    schemas: Dict[str, Any]
) -> List[Dict[str, str]]:
    """Generates complete TypeScript SDK files."""
    files = []

    # 1. src/types.ts
    types_lines = [
        "// Auto-generated TypeScript types by AgentFlow SDK Engine",
        "",
        "export interface ApiError {",
        "  statusCode: number;",
        "  message: string;",
        "  details?: unknown;",
        "}",
        "",
        "export interface RequestOptions {",
        "  headers?: Record<string, string>;",
        "  timeoutMs?: number;",
        "}",
        "",
    ]

    for model_name, model_def in schemas.items():
        pascal_name = _to_pascal_case(model_name)
        types_lines.append(f"export interface {pascal_name} {{")
        props = model_def.get("properties", {}) if isinstance(model_def, dict) else {}
        if not props:
            props = {"id": {"type": "string"}, "name": {"type": "string"}}
        for prop_name, prop_meta in props.items():
            prop_type = prop_meta.get("type", "string") if isinstance(prop_meta, dict) else "string"
            ts_type = "string"
            if prop_type in ["integer", "number"]:
                ts_type = "number"
            elif prop_type == "boolean":
                ts_type = "boolean"
            types_lines.append(f"  {prop_name}?: {ts_type};")
        types_lines.append("}")
        types_lines.append("")

    types_content = "\n".join(types_lines)
    files.append({"path": "src/types.ts", "content": types_content, "language": "typescript"})

    # 2. src/client.ts
    client_lines = [
        "// Auto-generated TypeScript SDK Client by AgentFlow",
        'import { RequestOptions } from "./types";',
        "",
        "export interface ClientConfig {",
        "  baseUrl: string;",
        "  apiKey?: string;",
        "  token?: string;",
        "}",
        "",
        "export class ApiClient {",
        "  private baseUrl: string;",
        "  private apiKey?: string;",
        "  private token?: string;",
        "",
        "  constructor(config: ClientConfig) {",
        "    this.baseUrl = config.baseUrl.replace(/\\/+$/, '');",
        "    this.apiKey = config.apiKey;",
        "    this.token = config.token;",
        "  }",
        "",
        "  private async request<T>(",
        "    method: string,",
        "    path: string,",
        "    body?: unknown,",
        "    options?: RequestOptions",
        "  ): Promise<T> {",
        "    const headers: Record<string, string> = {",
        "      'Content-Type': 'application/json',",
        "      'Accept': 'application/json',",
        "      ...(this.apiKey ? { 'X-API-Key': this.apiKey } : {}),",
        "      ...(this.token ? { 'Authorization': `Bearer ${this.token}` } : {}),",
        "      ...(options?.headers || {}),",
        "    };",
        "",
        "    const res = await fetch(`${this.baseUrl}${path}`, {",
        "      method,",
        "      headers,",
        "      body: body ? JSON.stringify(body) : undefined,",
        "    });",
        "",
        "    if (!res.ok) {",
        "      const errorBody = await res.text().catch(() => '');",
        "      throw new Error(`API Request Error ${res.status}: ${errorBody || res.statusText}`);",
        "    }",
        "",
        "    return res.json() as Promise<T>;",
        "  }",
        "",
    ]

    for route in routes:
        m = route["method"].upper()
        p = route["path"]
        method_name = _generate_method_name(m, p)
        desc = route.get("description", f"{m} {p}")
        has_id = "{" in p
        path_params = re.findall(r"\{([a-zA-Z0-9_]+)\}", p)

        param_sigs = [f"{param}: string | number" for param in path_params]
        if m in ["POST", "PUT", "PATCH"]:
            param_sigs.append("payload: Record<string, unknown>")
        param_sigs.append("options?: RequestOptions")
        param_str = ", ".join(param_sigs)

        # Template string path replacement
        ts_path = p
        for param in path_params:
            ts_path = ts_path.replace(f"{{{param}}}", f"${{{param}}}")

        client_lines.append(f"  /** {desc} */")
        client_lines.append(f"  async {method_name}({param_str}): Promise<unknown> {{")
        body_arg = "payload" if m in ["POST", "PUT", "PATCH"] else "undefined"
        client_lines.append(f"    return this.request('{m}', `{ts_path}`, {body_arg}, options);")
        client_lines.append("  }")
        client_lines.append("")

    client_lines.append("}")
    client_content = "\n".join(client_lines)
    files.append({"path": "src/client.ts", "content": client_content, "language": "typescript"})

    # 3. src/index.ts
    files.append({
        "path": "src/index.ts",
        "content": 'export * from "./types";\nexport * from "./client";\n',
        "language": "typescript"
    })

    # 4. package.json
    pkg_json = f"""{{
  "name": "@{project_slug}/client-sdk",
  "version": "1.0.0",
  "description": "Auto-generated TypeScript SDK for {project_slug}",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "scripts": {{
    "build": "tsc",
    "test": "echo \\"Running tests...\\" && exit 0"
  }},
  "keywords": ["agentflow", "sdk", "api-client", "typescript"],
  "license": "MIT",
  "devDependencies": {{
    "typescript": "^5.4.0"
  }}
}}"""
    files.append({"path": "package.json", "content": pkg_json, "language": "json"})

    # 5. README.md
    readme = f"""# @{project_slug}/client-sdk

Production-ready TypeScript SDK generated by AgentFlow.

## Installation

```bash
npm install @{project_slug}/client-sdk
# or with pnpm:
pnpm add @{project_slug}/client-sdk
```

## Quick Start

```typescript
import {{ ApiClient }} from "@{project_slug}/client-sdk";

const client = new ApiClient({{
  baseUrl: "https://api.example.com",
  token: process.env.API_TOKEN,
}});

async function main() {{
  const data = await client.listProjects();
  console.log("Projects:", data);
}}

main().catch(console.error);
```
"""
    files.append({"path": "README.md", "content": readme, "language": "markdown"})

    return files


def _generate_python_sdk(
    project_slug: str,
    routes: List[Dict[str, Any]],
    schemas: Dict[str, Any]
) -> List[Dict[str, str]]:
    """Generates complete Python SDK files."""
    files = []
    py_mod = project_slug.replace("-", "_")

    # 1. sdk/models.py
    models_lines = [
        "# Auto-generated Pydantic models by AgentFlow SDK Engine",
        "from typing import Optional, Dict, Any",
        "from pydantic import BaseModel, Field",
        "",
    ]
    for model_name, model_def in schemas.items():
        pascal_name = _to_pascal_case(model_name)
        models_lines.append(f"class {pascal_name}(BaseModel):")
        props = model_def.get("properties", {}) if isinstance(model_def, dict) else {}
        if not props:
            props = {"id": {"type": "string"}, "name": {"type": "string"}}
        for prop_name, prop_meta in props.items():
            prop_type = prop_meta.get("type", "string") if isinstance(prop_meta, dict) else "string"
            py_type = "str"
            if prop_type in ["integer", "number"]:
                py_type = "int" if prop_type == "integer" else "float"
            elif prop_type == "boolean":
                py_type = "bool"
            models_lines.append(f"    {prop_name}: Optional[{py_type}] = None")
        models_lines.append("")

    files.append({"path": f"{py_mod}/models.py", "content": "\n".join(models_lines), "language": "python"})

    # 2. sdk/client.py
    client_lines = [
        "# Auto-generated Python SDK Client by AgentFlow",
        "import httpx",
        "from typing import Optional, Dict, Any, Union",
        "",
        "class ApiClient:",
        "    def __init__(self, base_url: str = 'http://localhost:8000', api_key: Optional[str] = None, token: Optional[str] = None):",
        "        self.base_url = base_url.rstrip('/')",
        "        self.headers = {",
        "            'Content-Type': 'application/json',",
        "            'Accept': 'application/json',",
        "        }",
        "        if api_key:",
        "            self.headers['X-API-Key'] = api_key",
        "        if token:",
        "            self.headers['Authorization'] = f'Bearer {token}'",
        "",
        "    def _request(self, method: str, path: str, json: Optional[Dict[str, Any]] = None, **kwargs) -> Any:",
        "        with httpx.Client(base_url=self.base_url, headers=self.headers, timeout=30.0) as client:",
        "            res = client.request(method, path, json=json, **kwargs)",
        "            res.raise_for_status()",
        "            return res.json()",
        "",
    ]

    for route in routes:
        m = route["method"].upper()
        p = route["path"]
        method_name = _to_snake_case(_generate_method_name(m, p))
        desc = route.get("description", f"{m} {p}")
        path_params = re.findall(r"\{([a-zA-Z0-9_]+)\}", p)

        param_sigs = ["self"]
        for param in path_params:
            param_sigs.append(f"{param}: Union[str, int]")
        if m in ["POST", "PUT", "PATCH"]:
            param_sigs.append("payload: Optional[Dict[str, Any]] = None")
        param_str = ", ".join(param_sigs)

        py_path = p
        for param in path_params:
            py_path = py_path.replace(f"{{{param}}}", f"{{{param}}}")

        client_lines.append(f"    def {method_name}({param_str}) -> Any:")
        client_lines.append(f'        """{desc}"""')
        client_lines.append(f"        url = f'{py_path}'")
        json_arg = "json=payload" if m in ["POST", "PUT", "PATCH"] else ""
        args = [f"'{m}'", "url"]
        if json_arg:
            args.append(json_arg)
        client_lines.append(f"        return self._request({', '.join(args)})")
        client_lines.append("")

    files.append({"path": f"{py_mod}/client.py", "content": "\n".join(client_lines), "language": "python"})

    # 3. sdk/__init__.py
    files.append({
        "path": f"{py_mod}/__init__.py",
        "content": f"from .{py_mod}.client import ApiClient\n\n__all__ = ['ApiClient']\n",
        "language": "python"
    })

    # 4. pyproject.toml
    pyproject = f"""[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{project_slug}-sdk"
version = "1.0.0"
description = "Auto-generated Python SDK for {project_slug}"
readme = "README.md"
requires-python = ">=3.9"
dependencies = [
    "httpx>=0.27.0",
    "pydantic>=2.6.0"
]
"""
    files.append({"path": "pyproject.toml", "content": pyproject, "language": "toml"})

    # 5. README.md
    readme = f"""# {project_slug}-sdk

Python SDK generated by AgentFlow.

## Installation

```bash
pip install {project_slug}-sdk
```

## Quick Start

```python
from {py_mod} import ApiClient

client = ApiClient(
    base_url="https://api.example.com",
    token="YOUR_API_TOKEN"
)

response = client.list_projects()
print(response)
```
"""
    files.append({"path": "README.md", "content": readme, "language": "markdown"})

    return files


def _generate_curl_cheat_sheet(
    project_slug: str,
    routes: List[Dict[str, Any]]
) -> List[Dict[str, str]]:
    """Generates cURL command cheat sheet and REST client files."""
    files = []

    # 1. curl_recipes.sh
    sh_lines = [
        "#!/usr/bin/env bash",
        f"# cURL Recipes for {project_slug}",
        "API_BASE=\"http://localhost:8000\"",
        "TOKEN=\"your_jwt_token_here\"",
        "",
    ]

    for route in routes:
        m = route["method"].upper()
        p = route["path"]
        desc = route.get("description", f"{m} {p}")
        clean_p = p.replace("{id}", "1").replace("{projectId}", "1")

        sh_lines.append(f"# --- {desc} ---")
        if m == "GET":
            sh_lines.append(f"curl -X GET \"$API_BASE{clean_p}\" \\")
            sh_lines.append("  -H \"Authorization: Bearer $TOKEN\" \\")
            sh_lines.append("  -H \"Accept: application/json\"")
        elif m == "POST":
            sh_lines.append(f"curl -X POST \"$API_BASE{clean_p}\" \\")
            sh_lines.append("  -H \"Authorization: Bearer $TOKEN\" \\")
            sh_lines.append("  -H \"Content-Type: application/json\" \\")
            sh_lines.append("  -d '{\"name\": \"Sample Item\", \"description\": \"Created via cURL\"}'")
        elif m in ["PUT", "PATCH"]:
            sh_lines.append(f"curl -X {m} \"$API_BASE{clean_p}\" \\")
            sh_lines.append("  -H \"Authorization: Bearer $TOKEN\" \\")
            sh_lines.append("  -H \"Content-Type: application/json\" \\")
            sh_lines.append("  -d '{\"name\": \"Updated Item\"}'")
        elif m == "DELETE":
            sh_lines.append(f"curl -X DELETE \"$API_BASE{clean_p}\" \\")
            sh_lines.append("  -H \"Authorization: Bearer $TOKEN\"")
        sh_lines.append("")

    files.append({"path": "curl_recipes.sh", "content": "\n".join(sh_lines), "language": "bash"})

    # 2. endpoints.http (VS Code REST client format)
    http_lines = [
        f"### REST Client Recipes for {project_slug}",
        "@baseUrl = http://localhost:8000",
        "@token = your_token_here",
        "",
    ]
    for route in routes:
        m = route["method"].upper()
        p = route["path"]
        desc = route.get("description", f"{m} {p}")
        clean_p = p.replace("{id}", "1")
        http_lines.append(f"### {desc}")
        http_lines.append(f"{m} {{{{baseUrl}}}}{clean_p}")
        http_lines.append("Authorization: Bearer {{token}}")
        if m in ["POST", "PUT", "PATCH"]:
            http_lines.append("Content-Type: application/json")
            http_lines.append("")
            http_lines.append('{"name": "Sample", "status": "active"}')
        http_lines.append("")

    files.append({"path": "endpoints.http", "content": "\n".join(http_lines), "language": "http"})

    return files


def generate_project_sdk_bundle(
    project_id: Union[UUID, str],
    language: str,
    db: Session
) -> Dict[str, Any]:
    """Generates an SDK bundle for a specific language."""
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

    api_node = next((n for n in project.artifact_nodes if n.artifact_type == "API_SPEC"), None)
    db_node = next((n for n in project.artifact_nodes if n.artifact_type == "DB_SCHEMA"), None)

    api_text = "\n\n".join(s.content for s in api_node.sections) if api_node and api_node.sections else ""
    db_text = "\n\n".join(s.content for s in db_node.sections) if db_node and db_node.sections else ""

    routes = _extract_routes(api_text)
    schemas = _extract_schemas(db_text)
    project_slug = sanitize_project_slug(project.name)

    lang = language.lower()
    if lang in ["typescript", "ts", "javascript", "js"]:
        files = _generate_typescript_sdk(project_slug, routes, schemas)
        pkg_name = f"@{project_slug}/client-sdk"
        install_cmd = f"npm install @{project_slug}/client-sdk"
        snippet = f'import {{ ApiClient }} from "@{project_slug}/client-sdk";\nconst client = new ApiClient({{ baseUrl: "http://localhost:8000" }});\nawait client.listProjects();'
        res_lang = "typescript"
    elif lang in ["python", "py"]:
        files = _generate_python_sdk(project_slug, routes, schemas)
        pkg_name = f"{project_slug}-sdk"
        install_cmd = f"pip install {project_slug}-sdk"
        snippet = f'from {project_slug.replace("-", "_")} import ApiClient\nclient = ApiClient(base_url="http://localhost:8000")\nprojects = client.list_projects()'
        res_lang = "python"
    elif lang in ["curl", "bash", "cli"]:
        files = _generate_curl_cheat_sheet(project_slug, routes)
        pkg_name = f"{project_slug}-curl-recipes"
        install_cmd = f"chmod +x curl_recipes.sh && ./curl_recipes.sh"
        snippet = f'curl -X GET "http://localhost:8000/api/v1/projects" \\\n  -H "Authorization: Bearer $TOKEN"'
        res_lang = "curl"
    else:
        raise ValueError(f"Unsupported SDK language '{language}'. Supported: typescript, python, curl.")

    return {
        "project_id": project.id,
        "project_name": project.name,
        "language": res_lang,
        "package_name": pkg_name,
        "install_command": install_cmd,
        "readme_snippet": snippet,
        "files": files,
        "routes_count": len(routes),
    }


def generate_all_sdk_packages(
    project_id: Union[UUID, str],
    db: Session
) -> Dict[str, Any]:
    """Generates all SDK bundles (TypeScript, Python, cURL)."""
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

    ts_bundle = generate_project_sdk_bundle(target_id, "typescript", db)
    py_bundle = generate_project_sdk_bundle(target_id, "python", db)
    curl_bundle = generate_project_sdk_bundle(target_id, "curl", db)

    return {
        "project_id": project.id,
        "project_name": project.name,
        "available_languages": ["typescript", "python", "curl"],
        "packages": {
            "typescript": ts_bundle,
            "python": py_bundle,
            "curl": curl_bundle,
        }
    }
