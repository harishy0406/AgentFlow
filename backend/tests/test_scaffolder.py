"""
Tests for Phase 7 Code Scaffolding, Parsing, Patching, and ZIP Packaging
"""

import os
import shutil
import tempfile
from pathlib import Path
import pytest

from app.agents.scaffolder import (
    sanitize_project_slug,
    parse_code_files,
    scaffold_project_files,
    patch_project_files,
)


class TestProjectSlugSanitization:
    def test_basic_slug(self):
        assert sanitize_project_slug("My Cool App") == "my_cool_app"

    def test_special_characters_removed(self):
        assert sanitize_project_slug("E-Commerce @2026! Platform#") == "e_commerce_2026_platform"

    def test_empty_string_fallback(self):
        assert sanitize_project_slug("") == "agentflow_project"


class TestCodeFilesParser:
    def test_parse_multi_file_markdown(self):
        markdown_input = """
Here is the code:

### File: backend/models.py
```python
from sqlalchemy import Column, Integer, String
class User:
    id = Column(Integer, primary_key=True)
```

### File: backend/routes.py
```python
from fastapi import APIRouter
router = APIRouter()
```

### File: README.md
```markdown
# Documentation
```
"""
        parsed = parse_code_files(markdown_input)
        assert "backend/models.py" in parsed
        assert "backend/routes.py" in parsed
        assert "README.md" in parsed
        assert "class User:" in parsed["backend/models.py"]
        assert "router = APIRouter()" in parsed["backend/routes.py"]

    def test_fallback_when_no_file_headers(self):
        raw_code = "print('hello world')"
        parsed = parse_code_files(raw_code)
        assert "backend/main.py" in parsed
        assert parsed["backend/main.py"] == "print('hello world')"


class TestLocalDiskScaffolding:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_scaffold_project_files_creates_directories(self):
        sample_code = """
### File: backend/main.py
```python
from fastapi import FastAPI
app = FastAPI()
```

### File: frontend/App.jsx
```jsx
export default function App() { return <div>Hello</div>; }
```
"""
        res = scaffold_project_files(
            project_name="Ride Sharing App",
            code_content=sample_code,
            base_dir=self.temp_dir
        )

        assert res["project_slug"] == "ride_sharing_app"
        assert res["file_count"] >= 2
        
        target_path = Path(self.temp_dir) / "ride_sharing_app"
        assert (target_path / "backend" / "main.py").exists()
        assert (target_path / "frontend" / "App.jsx").exists()
        assert (target_path / "README.md").exists()

        # Check content
        with open(target_path / "backend" / "main.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "app = FastAPI()" in content

    def test_patch_project_files(self):
        initial_code = """
### File: backend/routes.py
```python
def get_users(): return []
```
"""
        scaffold_project_files("Patch Test", initial_code, base_dir=self.temp_dir)

        # Patch only backend/routes.py
        updated = {"backend/routes.py": "def get_users(): return ['Alice', 'Bob']"}
        patched = patch_project_files("Patch Test", updated, base_dir=self.temp_dir)

        assert "backend/routes.py" in patched
        target_path = Path(self.temp_dir) / "patch_test" / "backend" / "routes.py"
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Alice" in content
