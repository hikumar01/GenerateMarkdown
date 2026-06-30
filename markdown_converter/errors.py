from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConversionErrorCode(str, Enum):
    UNSUPPORTED = "unsupported"
    MISSING_TOOL = "missing_tool"
    EXTERNAL_COMMAND_FAILED = "external_command_failed"
    EMPTY_OUTPUT = "empty_output"
    UNSAFE_ARCHIVE = "unsafe_archive"
    ARCHIVE_EXTRACTION_FAILED = "archive_extraction_failed"
    ARCHIVE_CHILD_FAILURE = "archive_child_failure"
    EMBEDDED_PREVIEW_MISSING = "embedded_preview_missing"
    TRANSCRIPTION_FAILED = "transcription_failed"
    PACKAGE_EXTRACTION_FAILED = "package_extraction_failed"
    UNEXPECTED_ERROR = "unexpected_error"


@dataclass(frozen=True)
class ConversionIssue:
    code: ConversionErrorCode
    message: str
    detail: str = ""

    def render(self) -> str:
        if self.detail:
            return f"{self.message}: {self.detail} [{self.code.value}]"
        return f"{self.message} [{self.code.value}]"

    def as_dict(self) -> dict[str, str]:
        data = {"code": self.code.value, "message": self.message}
        if self.detail:
            data["detail"] = self.detail
        return data