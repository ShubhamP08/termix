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
import sys
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Ensure sibling packages (agent/, knowledge/, tools/, etc.) are importable
_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

# Load environment variables BEFORE any other imports that need them
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.graph import graph
from security.validator import validate_commands, contains_unresolved_placeholders
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
# Source formatting
# ---------------------------------------------------------------------------

def _format_source(source: str) -> str:
    return {
        "intent": "Deterministic (Intent Handler)",
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
    session_id: str = ""  # Optional session ID for persisting tool state

class ResolveResponse(BaseModel):
    commands: List[str]
    source: str
    source_display: str
    score: float = 0.0
    intent: str
    requires_confirmation: bool = False
    tool_name: str = ""
    missing_placeholders: List[str] = []
    tool_output: str = ""
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
    before execution.  The unified retrieval pipeline handles
    everything: intent detection, fuzzy, semantic, and LLM fallback.
    """
    instruction = (req.query or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="Empty query")

    # Ensure embeddings are ready (non-fatal if it fails)
    try:
        from knowledge.semantic import maybe_auto_rebuild_embeddings
        maybe_auto_rebuild_embeddings()
    except Exception:
        pass

    # ---- Run through the graph pipeline ----
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
    score = float(resolved.get("score") or 0.0)
    intent = resolved.get("intent", "unknown") or "unknown"
    requires_confirmation = bool(resolved.get("requires_confirmation", False))
    tool_name = resolved.get("tool_name") or ""
    missing_placeholders = list(resolved.get("missing_placeholders") or [])
    tool_output = resolved.get("tool_output") or ""

    if error:
        return ResolveResponse(
            commands=[],
            source=source,
            source_display=_format_source(source),
            score=score,
            intent=intent,
            requires_confirmation=requires_confirmation,
            tool_name=tool_name,
            missing_placeholders=missing_placeholders,
            error=error,
        )

    # Missing placeholder slots — return them so the frontend can prompt
    if missing_placeholders:
        return ResolveResponse(
            commands=[],
            source=source,
            source_display=_format_source(source),
            score=score,
            intent=intent,
            requires_confirmation=requires_confirmation,
            tool_name=tool_name,
            missing_placeholders=missing_placeholders,
        )

    if not commands and not tool_output:
        return ResolveResponse(
            commands=[],
            source=source,
            source_display=_format_source(source),
            score=score,
            intent="unknown",
            requires_confirmation=False,
            error="No commands generated.",
        )

    # Persist deferred tool state to session if present
    session_id = req.session_id
    if session_id and resolved.get("pending_tool"):
        sessions[session_id] = {
            "status": "resolved",
            "pending_tool": resolved.get("pending_tool"),
            "tool_name": tool_name,
            "source": source,
            "requires_confirmation": requires_confirmation,
            "commands": commands,
            "tool_output": tool_output,
            "rule_id": resolved.get("rule_id"),
        }
        logger.debug("[resolve] stored pending_tool in session %s", session_id)

    return ResolveResponse(
        commands=commands,
        source=source,
        source_display=_format_source(source),
        score=score,
        intent=intent,
        requires_confirmation=requires_confirmation,
        tool_name=tool_name,
        missing_placeholders=missing_placeholders,
        tool_output=tool_output,
    )


@app.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest):
    """
    Phase 2: Execute approved commands.

    Validates, executes, logs history, and returns structured results.
    First checks if session has pending_tool (deferred Python-native execution),
    otherwise falls through to standard shell execution.
    """
    session_id = req.session_id
    session = sessions.get(session_id) if session_id else None
    
    # Check for deferred tool execution in session
    if session and session.get("pending_tool"):
        from tools.tool_runner import execute_confirmed_tool
        
        pending_tool = session["pending_tool"]
        rule_id = pending_tool.get("rule_id", "")
        arguments = pending_tool.get("arguments", {})
        
        logger.debug("[execute] executing deferred tool: %s", rule_id)
        tool_result = execute_confirmed_tool(rule_id, arguments)
        
        # Convert ToolResult to ExecuteResponse format
        rendered_cmd = (tool_result.rendered_commands[0] if tool_result.rendered_commands else rule_id)
        results = [{
            "command": rendered_cmd,
            "success": not bool(tool_result.error),
            "output": tool_result.output,
            "error": tool_result.error,
        }]
        
        # Log history using rendered command if available, else rule id
        try:
            log_history(
                session.get("user_input", ""),
                tool_result.rendered_commands or [rule_id],
                session.get("source", ""),
            )
        except Exception:
            pass
        
        # Update session status
        session["status"] = "completed"
        
        return ExecuteResponse(
            results=results,
            line=f"[executor] Deferred tool executed: {rule_id}",
        )
    
    # Standard shell execution path
    command = (req.command or "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="Empty command")

    # Parse multiple commands if they come pipe-separated or as a single string
    # The frontend sends a single command string; the backend may have generated
    # multiple commands (stored as "; "-joined or separate).
    commands_to_run = [c.strip() for c in command.split("|||") if c.strip()] if "|||" in command else [command]

    if any(contains_unresolved_placeholders(cmd) for cmd in commands_to_run):
        return ExecuteResponse(
            results=[{
                "command": command,
                "success": False,
                "output": "",
                "error": "Blocked unresolved placeholder(s) in command template.",
            }],
            line="[executor] BLOCKED: unresolved placeholders",
        )

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
