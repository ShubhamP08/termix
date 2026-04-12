"""
Shell abstraction stub.

Intended to wrap subprocess execution and OS-specific behavior.
"""

from __future__ import annotations

import platform
import shlex
import subprocess
from typing import List

from security.validator import validate_commands


class Shell:
    def __init__(self, *, timeout: int = 30, live_logging: bool = False) -> None:
        self.timeout = timeout
        self.live_logging = live_logging

    def _is_windows(self) -> bool:
        return platform.system().lower().startswith("windows")

    def _tokenize_command(self, command: str) -> List[str]:
        # Parse with platform-appropriate rules while still avoiding shell=True.
        return shlex.split(command, posix=not self._is_windows())

    def _validate_command(self, command: str) -> bool:
        # Reuse project-level safety validation and block empty commands.
        if not command or not command.strip():
            return False
        return validate_commands([command])

    def run(self, command: str) -> dict:
        """
        Execute a command and return structured output.

        Security:
        - Uses shell=True to support pipes and shell operators.
        - Validates command before execution.
        """
        if self.live_logging:
            print(f"[shell] Running: {command}")

        try:
            if not command or not command.strip():
                return {
                    "success": False,
                    "output": "",
                    "error": "Empty command.",
                    "return_code": -1,
                }

            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=True,
            )
            return {
                "success": completed.returncode == 0,
                "output": completed.stdout or "",
                "error": completed.stderr or "",
                "return_code": int(completed.returncode),
            }
        except subprocess.TimeoutExpired as exc:
            stdout = ""
            stderr = ""
            if isinstance(exc.stdout, bytes):
                stdout = exc.stdout.decode("utf-8", errors="replace")
            elif isinstance(exc.stdout, str):
                stdout = exc.stdout
            if isinstance(exc.stderr, bytes):
                stderr = exc.stderr.decode("utf-8", errors="replace")
            elif isinstance(exc.stderr, str):
                stderr = exc.stderr

            return {
                "success": False,
                "output": stdout,
                "error": f"Command timed out after {self.timeout}s. {stderr}".strip(),
                "return_code": -1,
            }
        except Exception as exc:
            return {
                "success": False,
                "output": "",
                "error": str(exc),
                "return_code": -1,
            }

    def run_safe(self, command: str) -> dict:
        """
        Validate command before execution.
        """
        if not self._validate_command(command):
            return {
                "success": False,
                "output": "",
                "error": "Unsafe or invalid command blocked by validator.",
                "return_code": -1,
            }
        return self.run(command)

