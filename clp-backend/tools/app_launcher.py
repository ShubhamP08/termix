"""
App launcher tool with strict allowlist.

Only applications explicitly listed in ALLOWED_APPS may be launched.
If <app_name> is not in the allowlist, safe_to_execute=False is returned
with a clear error message.

All app launches require user confirmation (requires_confirmation=True).
Cross-platform: maps canonical names to OS-native launch commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tools.types import ToolResult
from utils.os_detector import detect_os


# ── Allowlist ────────────────────────────────────────────────────────────────
# Map: canonical_name → {os: shell_command}
# null means the app is not available on that OS.

ALLOWED_APPS: Dict[str, Dict[str, Optional[str]]] = {
    "vscode": {
        "linux":   "code",
        "macos":   "code",
        "windows": "code",
    },
    "code": {  # alias
        "linux":   "code",
        "macos":   "code",
        "windows": "code",
    },
    "chrome": {
        "linux":   "google-chrome",
        "macos":   "open -a 'Google Chrome'",
        "windows": "start chrome",
    },
    "google-chrome": {
        "linux":   "google-chrome",
        "macos":   "open -a 'Google Chrome'",
        "windows": "start chrome",
    },
    "safari": {
        "linux":   None,           # not available on Linux
        "macos":   "open -a Safari",
        "windows": None,           # not available on Windows
    },
    "firefox": {
        "linux":   "firefox",
        "macos":   "open -a Firefox",
        "windows": "start firefox",
    },
    "terminal": {
        "linux":   "x-terminal-emulator",
        "macos":   "open -a Terminal",
        "windows": "start cmd",
    },
    "finder": {
        "linux":   "xdg-open .",
        "macos":   "open .",
        "windows": "explorer .",
    },
    "file manager": {
        "linux":   "xdg-open .",
        "macos":   "open .",
        "windows": "explorer .",
    },
    "file-manager": {
        "linux":   "xdg-open .",
        "macos":   "open .",
        "windows": "explorer .",
    },
    "calculator": {
        "linux":   "gnome-calculator",
        "macos":   "open -a Calculator",
        "windows": "calc",
    },
    "calc": {  # alias
        "linux":   "gnome-calculator",
        "macos":   "open -a Calculator",
        "windows": "calc",
    },
    "notepad": {
        "linux":   "gedit",
        "macos":   "open -a TextEdit",
        "windows": "notepad",
    },
    "textedit": {
        "linux":   "gedit",
        "macos":   "open -a TextEdit",
        "windows": "notepad",
    },
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _os_key() -> str:
    os_name = detect_os()
    if os_name == "mac":
        return "macos"
    if os_name == "windows":
        return "windows"
    return "linux"


def normalize_app_name(raw: str) -> str:
    """Lowercase and strip the app name for allowlist lookup."""
    return (raw or "").strip().lower()


def is_allowed(app_name: str) -> bool:
    """Check if an app name is in the allowlist."""
    return normalize_app_name(app_name) in ALLOWED_APPS


def allowed_app_names() -> List[str]:
    """Return the canonical list of allowed app names."""
    return sorted(set(ALLOWED_APPS.keys()))


# ── Tool handlers ─────────────────────────────────────────────────────────────

def tool_open_app(app_name: str, *, in_current_dir: bool = False) -> ToolResult:
    """
    Launch a named application after allowlist validation.

    Parameters
    ----------
    app_name : str
        Application name from user query.  Must be in ALLOWED_APPS.
    in_current_dir : bool
        If True, pass "." as the argument to the app (open in current dir).

    Returns
    -------
    ToolResult
        - If app_name not in allowlist → safe_to_execute=False with error
        - If app not available on current OS → safe_to_execute=False
        - Otherwise → rendered_commands contains the OS command, requires_confirmation=True
    """
    if not app_name or not app_name.strip():
        return ToolResult(
            tool_name="open_app",
            missing_placeholders=["app_name"],
            safe_to_execute=False,
        )

    canonical = normalize_app_name(app_name)
    tool_label = "open_app_in_current_dir" if in_current_dir else "open_app"

    if canonical not in ALLOWED_APPS:
        allowed = ", ".join(sorted(ALLOWED_APPS.keys()))
        return ToolResult(
            tool_name=tool_label,
            arguments={"app_name": app_name},
            requires_confirmation=True,
            safe_to_execute=False,
            error=(
                f"'{app_name}' is not in the permitted app allowlist. "
                f"Allowed apps: {allowed}"
            ),
        )

    os_key = _os_key()
    base_cmd = ALLOWED_APPS[canonical].get(os_key)

    if base_cmd is None:
        return ToolResult(
            tool_name=tool_label,
            arguments={"app_name": app_name},
            requires_confirmation=True,
            safe_to_execute=False,
            error=f"'{app_name}' is not supported on {os_key}.",
        )

    # Append "." for in_current_dir variants (only if the command doesn't already target ".")
    if in_current_dir and not base_cmd.endswith("."):
        cmd = f"{base_cmd} ."
    else:
        cmd = base_cmd

    return ToolResult(
        tool_name=tool_label,
        arguments={"app_name": canonical},
        requires_confirmation=True,  # Always confirm app launches
        safe_to_execute=True,
        rendered_commands=[cmd],
    )
