import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def start():
    mailpit_exe = ROOT / "infra" / "mailpit" / "mailpit.exe"
    uvicorn_exe = ROOT / "venv" / "Scripts" / "uvicorn.exe"
    
    print("Checking Mailpit...")
    try:
        urllib.request.urlopen("http://127.0.0.1:8025/api/v1/messages", timeout=1)
        print("Mailpit already running.")
    except Exception:
        print("Starting Mailpit...")
        subprocess.Popen([str(mailpit_exe), "-s", "127.0.0.1:1025", "-l", "127.0.0.1:8025"], cwd=str(ROOT))
        time.sleep(1)

    print("Checking Backend...")
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
        print("Backend already running.")
    except Exception:
        print("Starting Backend...")
        env = os.environ.copy()
        env["PYTHONPATH"] = "backend"
        subprocess.Popen([str(uvicorn_exe), "src.api.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"], cwd=str(ROOT / "backend"), env=env)
        time.sleep(2)

    print("Checking Frontend...")
    try:
        urllib.request.urlopen("http://127.0.0.1:3000", timeout=1)
        print("Frontend already running.")
    except Exception:
        print("Starting Frontend...")
        subprocess.Popen(["npm.cmd", "run", "dev"], cwd=str(ROOT / "frontend"), shell=True)
        time.sleep(2)

if __name__ == "__main__":
    start()
