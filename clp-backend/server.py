"""
FastAPI server for CLP Terminal Agent.

Wraps the existing LangGraph pipeline and executor so the
React frontend (termix-cli) can call it over HTTP.

Run:
    cd clp-backend
    uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables BEFORE any other imports that need them
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.graph import graph
from utils.file_ops import build_filename, generate_file_commands, is_create_file_intent
from security.validator import validate_commands
from execution.executor import execute_commands
from utils.history_logger import log_history

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CLP Terminal Agent API",
    description="FastAPI server exposing the CLP terminal agent for the TermiX frontend.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory session store (for interactive command tracking)
# ---------------------------------------------------------------------------

sessions: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Source formatting (mirrors cli/main.py)
# ---------------------------------------------------------------------------

def _format_source(source: str) -> str:
    return {
        "kb_fuzzy": "Knowledge Base (Fuzzy Match)",
        "kb_semantic": "Knowledge Base (Semantic)",
        "llm": "LLM (Gemini)",
        "file_ops": "File Operations",
        "gemini": "LLM (Gemini)",
    }.get(source, source or "Unknown")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ResolveRequest(BaseModel):
    query: str

class ResolveResponse(BaseModel):
    commands: List[str]
    source: str
    source_display: str
    intent: str
    error: str = ""

class ExecuteRequest(BaseModel):
    session_id: str
    command: str  # kept for backwards compat — but we use commands from session
    source: str

class ExecuteResponse(BaseModel):
    results: List[Dict[str, Any]]
    line: str = ""

class InputRequest(BaseModel):
    session_id: str
    input: str

class StatusResponse(BaseModel):
    status: str  # 'idle' | 'completed' | 'running'


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "clp-terminal-agent"}


@app.post("/resolve", response_model=ResolveResponse)
async def resolve(req: ResolveRequest):
    """
    Phase 1: Resolve a natural-language query into commands.

    Runs the LangGraph pipeline with approved=False so it stops
    before execution — exactly like cli/main.py Phase 1.
    """
    instruction = (req.query or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="Empty query")

    # Ensure embeddings are ready
    try:
        from utils.kb import ensure_embeddings_exist
        ensure_embeddings_exist()
    except Exception:
        pass  # Non-fatal if embeddings setup fails

    # ---- Fast path: deterministic file-create ----
    if is_create_file_intent(instruction):
        filename = build_filename(instruction)
        commands = generate_file_commands(filename)

        if not validate_commands(commands):
            return ResolveResponse(
                commands=[],
                source="file_ops",
                source_display=_format_source("file_ops"),
                intent="file_op",
                error="Commands failed safety validation.",
            )

        return ResolveResponse(
            commands=commands,
            source="file_ops",
            source_display=_format_source("file_ops"),
            intent="file_op",
        )

    # ---- Normal path: graph Phase 1 ----
    initial_state: Dict[str, Any] = {
        "user_input": instruction,
        "commands": [],
        "validated": False,
        "approved": False,
        "execution_result": {},
        "error": "",
    }

    try:
        resolved = graph.invoke(initial_state)
    except Exception as exc:
        logger.error("Graph invoke failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Graph error: {exc}")

    commands = list(resolved.get("commands") or [])
    source = resolved.get("source") or ""
    error = resolved.get("error") or ""

    if error:
        return ResolveResponse(
            commands=[],
            source=source,
            source_display=_format_source(source),
            intent="unknown",
            error=error,
        )

    if not commands:
        return ResolveResponse(
            commands=[],
            source=source,
            source_display=_format_source(source),
            intent="unknown",
            error="No commands generated.",
        )

    return ResolveResponse(
        commands=commands,
        source=source,
        source_display=_format_source(source),
        intent=resolved.get("intent", "unknown") or "unknown",
    )


@app.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest):
    """
    Phase 2: Execute approved commands.

    Validates, executes, logs history, and returns structured results.
    """
    command = (req.command or "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="Empty command")

    # Parse multiple commands if they come pipe-separated or as a single string
    # The frontend sends a single command string; the backend may have generated
    # multiple commands (stored as "; "-joined or separate).
    commands_to_run = [c.strip() for c in command.split("|||") if c.strip()] if "|||" in command else [command]

    # Validate
    if not validate_commands(commands_to_run):
        return ExecuteResponse(
            results=[{
                "command": command,
                "success": False,
                "output": "",
                "error": "Unsafe command blocked.",
            }],
            line="[executor] BLOCKED: unsafe command",
        )

    # Execute
    results = execute_commands(commands_to_run)

    # Log history
    try:
        log_history(command, commands_to_run, req.source)
    except Exception:
        pass  # Non-fatal

    # Store session state
    sessions[req.session_id] = {
        "status": "completed",
        "results": results,
        "source": req.source,
    }

    # Build a summary line (like the CLI output)
    log_lines = []
    for r in results:
        status = "SUCCESS" if r.get("success") else "FAILED"
        log_lines.append(f"[executor] Command: {r['command']}")
        log_lines.append(f"[executor] {status}")

    return ExecuteResponse(
        results=results,
        line="\n".join(log_lines),
    )


@app.post("/input")
async def send_input(req: InputRequest):
    """
    Send stdin input to a running interactive process.

    For now, most commands are non-interactive (they complete immediately),
    so this is a stub that returns the session status.
    """
    session = sessions.get(req.session_id)
    if not session:
        return {"line": "No active session.", "status": "completed"}

    return {"line": "", "status": session.get("status", "completed")}


@app.get("/status", response_model=StatusResponse)
async def status(session_id: str = ""):
    """Return the status of a session."""
    session = sessions.get(session_id)
    if not session:
        return StatusResponse(status="completed")

    return StatusResponse(status=session.get("status", "completed"))


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    logger.info("CLP Terminal Agent API started on port 8000")
    logger.info("GEMINI_MODEL=%s", os.getenv("GEMINI_MODEL", "not set"))
