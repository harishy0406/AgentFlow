#!/usr/bin/env python3
"""
AgentFlow Unified Automated Launcher
====================================
Starts both the FastAPI Backend and Next.js Cyber Dashboard with a single command,
monitors startup health, launches the browser automatically, and provides clean
one-keystroke shutdown (Ctrl+C).
"""

import os
import sys
import time
import shutil
import signal
import socket
import threading
import subprocess
import webbrowser
import urllib.request
from pathlib import Path

# Safe encoding & buffering configuration
os.environ["PYTHONUNBUFFERED"] = "1"
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass
    # Enable ANSI escape sequences on Windows console
    os.system("")

# ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
DASHBOARD_DIR = ROOT_DIR / "dashboard"

processes = []
shutting_down = False


def log(msg, flush=True):
    print(msg, flush=flush)


def print_banner():
    banner = f"""{CYAN}{BOLD}
========================================================================
    _    ____ _____ _   _ _____ _____ _     _____        __
   / \\  / ___| ____| \\ | |_   _|  ___| |   / _ \\ \\      / /
  / _ \\| |  _|  _| |  \\| | | | | |_  | |  | | | \\ \\ /\\ / / 
 / ___ \\ |_| | |___| |\\  | | | |  _| | |__| |_| |\\ V  V /  
/_/   \\_\\____|_____|_| \\_| |_| |_|   |_____\\___/  \\_/\\_/   
========================================================================{RESET}
  {BOLD}AgentFlow{RESET} - {DIM}Autonomous Multi-Agent Workflow Orchestration Platform{RESET}
  {DIM}[v0.8.0] LangGraph DAG Engine | AST Verification | Multi-Model Fleet{RESET}
"""
    log(banner)


def is_port_in_use(port: int) -> bool:
    """Check if a network port is currently listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port(port: int):
    """Terminates any existing process holding the specified port."""
    if not is_port_in_use(port):
        return
    log(f"{YELLOW}[Port Manager] Port {port} is occupied by an existing process. Reclaiming...{RESET}")
    if os.name == "nt":
        try:
            cmd = f'powershell -Command "Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique"'
            output = subprocess.check_output(cmd, shell=True).decode().strip()
            for line in output.splitlines():
                pid = line.strip()
                if pid and pid.isdigit():
                    subprocess.run(["taskkill", "/F", "/T", "/PID", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    time.sleep(1)


def get_python_executable():
    """Finds virtualenv Python or falls back to current sys.executable."""
    if os.name == "nt":
        venv_py = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
    else:
        venv_py = BACKEND_DIR / "venv" / "bin" / "python"
    
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def get_npm_executable():
    """Finds npm command path."""
    npm_cmd = shutil.which("npm.cmd") if os.name == "nt" else shutil.which("npm")
    if not npm_cmd:
        npm_cmd = "npm"
    return npm_cmd


def check_prerequisites():
    """Validates node and python environments."""
    py_exe = get_python_executable()
    npm_exe = get_npm_executable()

    log(f"{DIM}[Setup]{RESET} Python runtime: {py_exe}")
    log(f"{DIM}[Setup]{RESET} NPM executable: {npm_exe}")

    # Check if dashboard node_modules exists
    node_modules = DASHBOARD_DIR / "node_modules"
    if not node_modules.exists():
        log(f"{YELLOW}[Setup] node_modules not found. Installing dashboard dependencies...{RESET}")
        subprocess.run([npm_exe, "install"], cwd=str(DASHBOARD_DIR), check=True)

    return py_exe, npm_exe


def stream_logs(process, prefix, color):
    """Streams stdout/stderr from a child process with colored prefix."""
    try:
        for line in iter(process.stdout.readline, ""):
            if shutting_down:
                break
            text = line.rstrip()
            if text:
                log(f"{color}{BOLD}[{prefix}]{RESET} {text}")
    except Exception:
        pass


def kill_process_tree(proc):
    """Kills process and all its children across Windows/Linux."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc.terminate()
    except Exception:
        pass


def cleanup(signum=None, frame=None):
    """Graceful shutdown handler for Ctrl+C."""
    global shutting_down
    if shutting_down:
        return
    shutting_down = True
    log(f"\n\n{YELLOW}{BOLD}[AgentFlow] Shutting down all services...{RESET}")
    for proc in processes:
        kill_process_tree(proc)
    log(f"{GREEN}[AgentFlow] All services stopped cleanly. Goodbye!{RESET}")
    sys.exit(0)


def wait_for_service(url, name, timeout=30):
    """Polls a service URL until HTTP 200 is received or timeout occurs."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if shutting_down:
            return False
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AgentFlow-HealthCheck"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main():
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print_banner()

    # Ensure ports 8000 & 3000 are not blocked by zombie processes
    free_port(8000)
    free_port(3000)

    py_exe, npm_exe = check_prerequisites()

    log(f"\n{CYAN}{BOLD}>> Starting Backend (FastAPI on :8000)...{RESET}")
    backend_proc = subprocess.Popen(
        [py_exe, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )
    processes.append(backend_proc)

    log(f"{GREEN}{BOLD}>> Starting Dashboard (Next.js on :3000)...{RESET}")
    dashboard_proc = subprocess.Popen(
        [npm_exe, "run", "dev"],
        cwd=str(DASHBOARD_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )
    processes.append(dashboard_proc)

    # Start background streaming threads
    t_backend = threading.Thread(target=stream_logs, args=(backend_proc, "BACKEND", CYAN), daemon=True)
    t_dash = threading.Thread(target=stream_logs, args=(dashboard_proc, "DASHBOARD", GREEN), daemon=True)
    t_backend.start()
    t_dash.start()

    # Health check watcher in separate thread to not block log streaming
    def health_and_open_browser():
        log(f"\n{DIM}[Status] Waiting for services to initialize...{RESET}")
        backend_ok = wait_for_service("http://localhost:8000/", "Backend", timeout=30)
        dashboard_ok = wait_for_service("http://localhost:3000/", "Dashboard", timeout=30)

        if backend_ok and dashboard_ok:
            msg = f"""
{GREEN}{BOLD}========================================================================
   [OK] AgentFlow v0.8.0 is LIVE and Ready!
========================================================================{RESET}
  {BOLD}* Dashboard UI:{RESET}     {GREEN}http://localhost:3000{RESET}
  {BOLD}* FastAPI Backend:{RESET}  {CYAN}http://localhost:8000{RESET}
  {BOLD}* API Documentation:{RESET} {CYAN}http://localhost:8000/docs{RESET}
  {BOLD}* OpenAPI 3.0 Spec:{RESET}  {CYAN}http://localhost:8000/openapi.json{RESET}
{DIM}------------------------------------------------------------------------
  Press [Ctrl + C] at any time to gracefully stop all services.
========================================================================{RESET}
"""
            log(msg)
            # Automatically launch the browser
            try:
                webbrowser.open("http://localhost:3000")
            except Exception:
                pass
        else:
            if not backend_ok:
                log(f"{RED}[Warning] Backend health check timed out on http://localhost:8000/{RESET}")
            if not dashboard_ok:
                log(f"{RED}[Warning] Dashboard health check timed out on http://localhost:3000/{RESET}")

    threading.Thread(target=health_and_open_browser, daemon=True).start()

    # Keep main thread alive waiting for child process exits or Ctrl+C
    try:
        while True:
            if backend_proc.poll() is not None and not shutting_down:
                log(f"{RED}[Error] Backend process terminated unexpectedly (code {backend_proc.returncode}).{RESET}")
                cleanup()
            if dashboard_proc.poll() is not None and not shutting_down:
                log(f"{RED}[Error] Dashboard process terminated unexpectedly (code {dashboard_proc.returncode}).{RESET}")
                cleanup()
            time.sleep(0.5)
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
