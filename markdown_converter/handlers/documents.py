from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ..archive import extract_zip_safe
from ..capabilities import ConverterCapability
from ..errors import ConversionErrorCode, ConversionIssue
from ..results import ConverterResult


class DocumentHandlerMixin:
    def _markitdown(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        result = self.tools.run(["markitdown", source, "-o", dest])
        if not result.ok:
            return ConverterResult.failed(ConversionErrorCode.EXTERNAL_COMMAND_FAILED, result.short_error)
        return ConverterResult()

    def _xlsm(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            workbook = tmp / "book.xlsx"
            shutil.copy2(source, workbook)
            return self._markitdown(workbook, dest, ext, capability)

    def _libreoffice_then_markitdown(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        target = capability.target_by_ext[ext]
        if not self.tools.soffice:
            return ConverterResult.failed(ConversionErrorCode.MISSING_TOOL, "needs LibreOffice", "brew install --cask libreoffice")
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            result = self.tools.run(
                [
                    self.tools.soffice,
                    "--headless",
                    f"-env:UserInstallation=file://{tmp / 'lo'}",
                    "--convert-to",
                    target,
                    "--outdir",
                    tmp,
                    source,
                ],
                quiet=True,
            )
            if not result.ok:
                return ConverterResult.failed(ConversionErrorCode.EXTERNAL_COMMAND_FAILED, "LibreOffice conversion failed")
            converted = tmp / f"{source.stem}.{target}"
            if not converted.exists():
                candidates = sorted(tmp.glob(f"*.{target}"))
                converted = candidates[0] if candidates else converted
            if not converted.exists():
                return ConverterResult.failed(ConversionErrorCode.EXTERNAL_COMMAND_FAILED, "LibreOffice did not produce the expected output")
            return self._markitdown(converted, dest, ext, capability)

    def _rtf(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            html = tmp / "x.html"
            result = self.tools.run(["textutil", "-convert", "html", "-output", html, source], quiet=True)
            if not result.ok:
                return ConverterResult.failed(ConversionErrorCode.EXTERNAL_COMMAND_FAILED, result.short_error)
            return self._markitdown(html, dest, ext, capability)

    def _pages(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            extraction = extract_zip_safe(source, tmp)
            if not extraction.ok:
                issue = extraction.issue or ConversionIssue(ConversionErrorCode.ARCHIVE_EXTRACTION_FAILED, "could not extract Pages document")
                return ConverterResult(success=False, produced=False, issue=issue)
            preview = tmp / "QuickLook" / "Preview.pdf"
            if not preview.exists():
                return ConverterResult.failed(ConversionErrorCode.EMBEDDED_PREVIEW_MISSING, "no embedded preview", "re-save with 'Include preview in document'")
            return self._markitdown(preview, dest, ext, capability)