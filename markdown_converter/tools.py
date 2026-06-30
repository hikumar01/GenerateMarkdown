from __future__ import annotations

import importlib.util
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def short_error(self) -> str:
        text = (self.stderr or self.stdout).strip()
        if not text:
            return "conversion failed"
        line = text.splitlines()[-1].strip()
        return line or "conversion failed"


class ToolRunner:
    def __init__(self) -> None:
        self.soffice = self._find_soffice()

    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def exists(self, name: str) -> bool:
        if name.startswith("python:"):
            return importlib.util.find_spec(name.split(":", 1)[1]) is not None
        return self.which(name) is not None

    def run(
        self,
        args: Sequence[str | Path],
        *,
        cwd: Path | None = None,
        capture: bool = True,
        quiet: bool = False,
    ) -> CommandResult:
        str_args = [str(arg) for arg in args]
        try:
            completed = subprocess.run(
                str_args,
                cwd=str(cwd) if cwd else None,
                check=False,
                text=True,
                stdout=subprocess.DEVNULL if quiet else (subprocess.PIPE if capture else None),
                stderr=subprocess.DEVNULL if quiet else (subprocess.PIPE if capture else None),
            )
        except FileNotFoundError:
            return CommandResult(127, stderr=f"{str_args[0]} not found")
        return CommandResult(completed.returncode, completed.stdout or "", completed.stderr or "")

    def warn_missing(self, tools: Iterable[str] | None = None) -> list[str]:
        missing = []
        checked_tools = ("markitdown", "python3", "mlx_whisper", "ffprobe", "tesseract") if tools is None else tools
        for tool in checked_tools:
            if tool == "soffice":
                if not self.soffice:
                    missing.append("soffice(LibreOffice)")
            elif not self.exists(tool):
                missing.append(format_tool_name(tool))
        return missing

    def _find_soffice(self) -> str | None:
        found = self.which("soffice")
        if found:
            return found
        app_path = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if app_path.exists() and app_path.is_file():
            return str(app_path)
        return None


def format_command(args: Iterable[str | Path]) -> str:
    return " ".join(str(arg) for arg in args)


def format_tool_name(name: str) -> str:
    if name == "python:psd_tools":
        return "psd-tools"
    if name.startswith("python:"):
        return name.split(":", 1)[1]
    return name
