"""
Phase 7: Project Code Scaffolding & Local Disk Persistence Engine

Parses generated multi-file code blocks and writes runnable project repositories
directly to local disk under `generated_projects/<project_slug>/`.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Any


def sanitize_project_slug(project_name: str) -> str:
    """Convert project name into a clean, filesystem-safe directory slug."""
    slug = re.sub(r"[^a-zA-Z0-9_\-\s]", "", project_name).strip()
    slug = re.sub(r"[\s\-]+", "_", slug).lower()
    return slug or "agentflow_project"


def parse_code_files(raw_text: str) -> Dict[str, str]:
    """
    Parses multi-file markdown outputs in the format:
    
    ### File: backend/models.py
    ```python
    ... code ...
    ```
    
    Returns a dictionary of { relative_file_path: file_content }.
    """
    files: Dict[str, str] = {}
    
    # Pattern matching "### File: <path>\n```<lang>\n<code>\n```"
    pattern = re.compile(
        r"###\s+File:\s*([^\n\r]+)[\r\n]+```(?:[a-zA-Z0-9_-]+)?[\r\n]([\s\S]*?)```",
        re.IGNORECASE
    )
    
    matches = pattern.findall(raw_text)
    for file_path, content in matches:
        clean_path = file_path.strip().replace("\\", "/").lstrip("/")
        files[clean_path] = content.strip()

    # Fallback if model generated raw code without "### File:" headers
    if not files and raw_text.strip():
        files["backend/main.py"] = raw_text.strip()

    return files


def scaffold_project_files(
    project_name: str,
    code_content: str,
    base_dir: str = "generated_projects"
) -> Dict[str, Any]:
    """
    Writes parsed source code files directly to local disk.
    
    Returns metadata including target directory path and list of files written.
    """
    slug = sanitize_project_slug(project_name)
    target_dir = Path(base_dir) / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    files_dict = parse_code_files(code_content)
    files_written: List[str] = []

    for rel_path, content in files_dict.items():
        dest_path = target_dir / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(content)
        files_written.append(rel_path)

    # Always ensure a basic README is present if not already created
    readme_path = target_dir / "README.md"
    if not readme_path.exists():
        readme_content = f"# {project_name}\n\nGenerated automatically by **AgentFlow Orchestrator**.\n\n## Getting Started\nCheck `backend/` and `frontend/` directories."
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)
        files_written.append("README.md")

    return {
        "project_slug": slug,
        "target_path": str(target_dir.resolve()),
        "files_written": files_written,
        "file_count": len(files_written),
    }


def patch_project_files(
    project_name: str,
    updated_files: Dict[str, str],
    base_dir: str = "generated_projects"
) -> List[str]:
    """
    Selectively updates only the specified files on disk (diff-aware patching).
    """
    slug = sanitize_project_slug(project_name)
    target_dir = Path(base_dir) / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    patched: List[str] = []
    for rel_path, content in updated_files.items():
        dest_path = target_dir / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(content)
        patched.append(rel_path)

    return patched
