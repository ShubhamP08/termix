"""
Execution stub.

Responsible for executing validated commands with timeout/sandbox configuration.
"""

from __future__ import annotations

from typing import Any, Dict, List

from agent.state import AgentState
from execution.shell import Shell

try:
    from security.validator import validate_commands as _external_validate_commands
except Exception:  # pragma: no cover - fallback path
    _external_validate_commands = None


DANGEROUS_PATTERNS = ["rm -rf", "shutdown", "reboot", "mkfs"]


def _is_command_safe(command: str) -> bool:
    """
    Validate command safety using external validator when available,
    with an internal deny-list fallback.
    """
    normalized = (command or "").strip()
    if not normalized:
        return False

    lowered = normalized.lower()
    if any(pattern in lowered for pattern in DANGEROUS_PATTERNS):
        return False

    if _external_validate_commands is not None:
        try:
            return bool(_external_validate_commands([normalized]))
        except Exception:
            return False

    return True


def execute_commands(commands: List[str] | str, dry_run: bool = False, verbose: bool = True) -> List[dict]:
    """
    Execute commands sequentially with fail-fast behavior.

    Returns:
    [
      {
        "command": str,
        "success": bool,
        "output": str,
        "error": str
      }
    ]
    """
    shell = Shell(live_logging=False)
    results: List[dict] = []

    # Compatibility: allow either a single command string or a list of commands.
    normalized_commands = [commands] if isinstance(commands, str) else list(commands)

    for raw_command in normalized_commands:
        command = (raw_command or "").strip()

        if verbose:
            print(f"[executor] Command: {command}")

        if not _is_command_safe(command):
            result = {
                "command": command,
                "success": False,
                "output": "",
                "error": "Unsafe command blocked before execution.",
            }
            results.append(result)
            if verbose:
                print("[executor] BLOCKED: unsafe command")
            break

        if dry_run:
            result = {
                "command": command,
                "success": True,
                "output": "[DRY RUN] Command not executed.",
                "error": "",
            }
            results.append(result)
            if verbose:
                print("[executor] DRY RUN: skipped execution")
            continue

        shell_result = shell.run(command)
        result = {
            "command": command,
            "success": bool(shell_result.get("success", False)),
            "output": str(shell_result.get("output", "")),
            "error": str(shell_result.get("error", "")),
        }
        results.append(
            result
        )

        if result["success"]:
            if verbose:
                print("[executor] SUCCESS")
        else:
            if verbose:
                print("[executor] FAILED")
            break
        # print(results)
    return results


def execute(state: AgentState) -> AgentState:
    raw_commands = state.get("commands")
    if isinstance(raw_commands, str):
        commands = [raw_commands]
    else:
        commands = list(raw_commands or [])
    if not commands:
        proposed = (state.get("proposed_command") or "").strip()
        commands = [proposed] if proposed else []

    if not commands:
        state["execution_result"] = []
        return state

    state["execution_result"] = execute_commands(commands, dry_run=False, verbose=False)
    return state

