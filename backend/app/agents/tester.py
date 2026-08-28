"""
Phase 7: Code Verification & Automated Smoke Test Engine

Performs static analysis, AST validation, and smoke verification on scaffolded
application source code files in `generated_projects/<project_slug>/`.
"""

import ast
import json
import os
from pathlib import Path
from typing import Dict, List, Any


def verify_file_content(rel_path: str, content: str) -> Dict[str, Any]:
    """
    Validates a single file's content based on its file extension.
    Checks Python AST syntax, JSON validity, and basic markdown structure.
    """
    line_count = len(content.splitlines())
    
    if rel_path.endswith(".py"):
        try:
            tree = ast.parse(content, filename=rel_path)
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            details = []
            if classes:
                details.append(f"{len(classes)} class(es)")
            if functions:
                details.append(f"{len(functions)} function(s)")
            desc = f"Valid Python syntax ({', '.join(details) if details else 'module code'})"
            return {
                "path": rel_path,
                "file_type": "python",
                "status": "passed",
                "message": desc,
                "line_count": line_count,
                "symbols_count": len(classes) + len(functions),
            }
        except SyntaxError as e:
            return {
                "path": rel_path,
                "file_type": "python",
                "status": "failed",
                "message": f"Syntax Error at line {e.lineno}: {e.msg}",
                "line_count": line_count,
                "symbols_count": 0,
            }

    elif rel_path.endswith(".json"):
        try:
            json.loads(content)
            return {
                "path": rel_path,
                "file_type": "json",
                "status": "passed",
                "message": "Valid JSON schema/configuration",
                "line_count": line_count,
                "symbols_count": 0,
            }
        except Exception as e:
            return {
                "path": rel_path,
                "file_type": "json",
                "status": "failed",
                "message": f"Invalid JSON: {str(e)}",
                "line_count": line_count,
                "symbols_count": 0,
            }

    elif rel_path.endswith(".md"):
        is_valid = len(content.strip()) > 0
        return {
            "path": rel_path,
            "file_type": "markdown",
            "status": "passed" if is_valid else "failed",
            "message": "Valid Markdown specification" if is_valid else "Empty documentation file",
            "line_count": line_count,
            "symbols_count": 0,
        }

    else:
        # Default pass for JS, JSX, SQL, etc.
        return {
            "path": rel_path,
            "file_type": "generic",
            "status": "passed" if len(content.strip()) > 0 else "failed",
            "message": "Code file present and non-empty",
            "line_count": line_count,
            "symbols_count": 0,
        }


def verify_project_codebase(
    project_slug: str,
    base_dir: str = "generated_projects",
    fallback_files: List[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Performs automated static verification across all project files.
    """
    local_dir = Path(base_dir) / project_slug
    file_results: List[Dict[str, Any]] = []

    if local_dir.exists():
        for root, _, filenames in os.walk(local_dir):
            for filename in filenames:
                file_path = Path(root) / filename
                rel_path = str(file_path.relative_to(local_dir)).replace("\\", "/")
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    res = verify_file_content(rel_path, content)
                    file_results.append(res)
                except Exception as e:
                    file_results.append({
                        "path": rel_path,
                        "file_type": "unknown",
                        "status": "failed",
                        "message": f"Read error: {str(e)}",
                        "line_count": 0,
                        "symbols_count": 0,
                    })
    elif fallback_files:
        for file_item in fallback_files:
            res = verify_file_content(file_item["path"], file_item["content"])
            file_results.append(res)

    total_files = len(file_results)
    passed_files = sum(1 for r in file_results if r["status"] == "passed")
    failed_files = total_files - passed_files
    all_passed = total_files > 0 and failed_files == 0

    return {
        "project_slug": project_slug,
        "all_passed": all_passed,
        "total_files": total_files,
        "passed_files": passed_files,
        "failed_files": failed_files,
        "verification_score_pct": round((passed_files / total_files * 100) if total_files > 0 else 0.0, 1),
        "results": file_results,
    }
