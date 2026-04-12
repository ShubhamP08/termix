"""
OS detection stub.
"""

from __future__ import annotations

import platform


def detect_os() -> str:
    """
    Detect the current operating system.

    Returns one of: "linux", "windows", "mac", or "unknown".
    """
    system = platform.system().strip().lower()

    if system in {"darwin", "mac", "macos"}:
        return "mac"
    if system.startswith("win") or system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    return "unknown"

