"""
CareLoop Console Web Server
Hosts the Clinician Approval Inbox and Real-Time Ops Monitoring Dashboard.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="CareLoop Console & Approval Inbox", version="1.0.0")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def get_dashboard():
    return FileResponse(str(STATIC_DIR / "index.html"))

@app.get("/health")
def health():
    return {"status": "ok", "service": "careloop-console"}
