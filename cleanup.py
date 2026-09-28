#!/usr/bin/env python
"""
AgentFlow Temporary File Cleanup Utility
==========================================

Removes temporary files that are not needed in production environments:
- SQLite temporary lock files
- Python bytecode cache files
- Test artifacts
- Unnecessary generated files
"""

import os
import shutil
from pathlib import Path

def cleanup_sqlite_files():
    """Remove SQLite temporary lock files"""
    print("🧹 Cleaning SQLite temporary files...")

    sqlite_files = ['agentflow.db-shm', 'agentflow.db-wal']

    for file in sqlite_files:
        path = Path('backend') / file
        if path.exists():
            try:
                path.unlink()
                print(f"   ✅ Removed: {file}")
            except Exception as e:
                print(f"   ❌ Failed to remove {file}: {e}")

def cleanup_python_cache():
    """Remove Python bytecode cache files"""
    print("\n🧹 Cleaning Python cache files...")

    cache_dirs = [
        'backend/app/__pycache__',
        'backend/app/agents/__pycache__',
        'backend/app/eval/__pycache__',
        'backend/__pycache__',
        '__pycache__'
    ]

    for cache_dir in cache_dirs:
        path = Path(cache_dir)
        if path.exists():
            try:
                shutil.rmtree(path)
                print(f"   ✅ Removed: {cache_dir}")
            except Exception as e:
                print(f"   ❌ Failed to remove {cache_dir}: {e}")

def cleanup_test_artifacts():
    """Remove test-related files that shouldn't be in production"""
    print("\n🧹 Cleaning test artifacts...")

    test_files = [
        'fix_backend.py',
        'fix_issues.py',
        'test_backend.py',
        'cleanup.py',
        'fix_summary.txt'
    ]

    for file in test_files:
        path = Path(file)
        if path.exists():
            try:
                path.unlink()
                print(f"   ✅ Removed: {file}")
            except Exception as e:
                print(f"   ❌ Failed to remove {file}: {e}")

def cleanup_generated_files():
    """Remove unnecessary generated files"""
    print("\n🧹 Cleaning generated files...")

    # These might be intentionally generated, so we'll list them instead of deleting
    generated_dirs = [
        'generated_projects',
        'backend/generated_projects'
    ]

    for gen_dir in generated_dirs:
        path = Path(gen_dir)
        if path.exists():
            print(f"   ℹ️  Generated projects directory found: {gen_dir}")
            print(f"      You may want to review this directory before production deployment")

def cleanup_markdown_docs():
    """Remove temporary documentation files"""
    print("\n🧹 Cleaning temporary documentation...")

    doc_files = [
        'BACKEND_FIX_GUIDE.md',
        'SOLUTION.md',
        'VERIFICATION.md'
    ]

    for file in doc_files:
        path = Path(file)
        if path.exists():
            try:
                path.unlink()
                print(f"   ✅ Removed: {file}")
            except Exception as e:
                print(f"   ❌ Failed to remove {file}: {e}")

def cleanup_pytest_cache():
    """Remove pytest cache"""
    print("\n🧹 Cleaning pytest cache...")

    pytest_dirs = [
        'backend/.pytest_cache',
        '.pytest_cache'
    ]

    for pytest_dir in pytest_dirs:
        path = Path(pytest_dir)
        if path.exists():
            try:
                shutil.rmtree(path)
                print(f"   ✅ Removed: {pytest_dir}")
            except Exception as e:
                print(f"   ❌ Failed to remove {pytest_dir}: {e}")

def cleanup_logs():
    """Clean up log files"""
    print("\n🧹 Cleaning log files...")

    log_files = [
        'backend/*.log',
        'backend/app/*.log'
    ]

    for pattern in log_files:
        path = Path('backend/app') if 'backend/app' in pattern else Path('backend')
        files = list(path.glob('*.log'))

        for log_file in files:
            try:
                log_file.unlink()
                print(f"   ✅ Removed: {log_file.name}")
            except Exception as e:
                print(f"   ❌ Failed to remove {log_file.name}: {e}")

def safe_cleanup():
    """Safe cleanup that won't accidentally delete production data"""
    print("=" * 60)
    print("🚮 AgentFlow Temporary File Cleanup")
    print("=" * 60)

    # Only clean up files that are safe to remove in any environment
    cleanup_sqlite_files()
    cleanup_python_cache()
    cleanup_pytest_cache()
    cleanup_logs()
    cleanup_test_artifacts()
    cleanup_markdown_docs()

    print("\n" + "=" * 60)
    print("✅ Cleanup completed!")
    print("=" * 60)
    print("\n📋 Summary:")
    print("- SQLite lock files removed")
    print("- Python cache cleared")
    print("- Test artifacts cleaned")
    print("- Temporary documentation removed")
    print("- Pytest cache cleared")
    print("- Log files cleaned")
    print("\n🎉 Your environment is now production-ready!")

if __name__ == '__main__':
    safe_cleanup()