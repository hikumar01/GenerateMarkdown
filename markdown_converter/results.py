from __future__ import annotations

from dataclasses import dataclass

from .errors import ConversionErrorCode, ConversionIssue


@dataclass
class ConverterResult:
    success: bool = True
    produced: bool = True
    issue: ConversionIssue | None = None

    @property
    def reason(self) -> str:
        return self.issue.render() if self.issue else ""

    @classmethod
    def skipped(cls) -> "ConverterResult":
        return cls(success=True, produced=False)

    @classmethod
    def failed(cls, code: ConversionErrorCode, message: str, detail: str = "") -> "ConverterResult":
        return cls(success=False, produced=False, issue=ConversionIssue(code, message, detail))