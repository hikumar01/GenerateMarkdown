from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .archive import extract_zip_safe
from .capabilities import ARCHIVE_EXTS, CAPABILITY_BY_EXT
from .config import Settings
from .converters import ConverterRegistry
from .errors import ConversionErrorCode, ConversionIssue
from .manifest import HashManifest
from .report import ConversionReport
from .tools import ToolRunner


class MarkdownConverter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tools = ToolRunner()
        self.manifest = HashManifest(settings.out / ".convert_hashes")
        self.report = ConversionReport()
        self.registry = ConverterRegistry(settings, self.tools)

    def run(self) -> int:
        source_exts = self._scan_extensions(self.settings.src)
        self._print_preflight_warnings(source_exts)
        if self.settings.force:
            print("(force mode: reconverting everything)")
        print(f"Converting '{self.settings.src}'  ->  '{self.settings.out}'   (change detection: content hash)")
        print()
        self._walk(self.settings.src, self.settings.out)
        self.manifest.write()
        report_path = self.settings.out / "_conversion_report.json"
        text = self.report.render(self.settings.src, self.settings.out, self.settings.force)
        print(text, end="")
        self.report.write_json(report_path, self.settings.src, self.settings.out, self.settings.force)
        (self.settings.out / "_conversion_report.txt").unlink(missing_ok=True)
        print()
        print(f"Output: {self.settings.out}   (report saved to {report_path})")
        return 0

    def _walk(self, src: Path, out: Path, prefix: str = "") -> None:
        for current, dirs, files in os.walk(src):
            dirs[:] = sorted(dir_name for dir_name in dirs if not self._is_pruned_name(dir_name))
            current_path = Path(current)
            for file_name in sorted(files):
                if self._is_pruned_name(file_name):
                    continue
                source = current_path / file_name
                if source.is_symlink() or not source.is_file():
                    continue
                rel = source.relative_to(src)
                display_path = f"{prefix}{rel.as_posix()}"
                dest_dir = out / rel.parent
                dest_dir.mkdir(parents=True, exist_ok=True)
                ext = extension_for(source.name)
                if ext in ARCHIVE_EXTS:
                    self._convert_zip(source, dest_dir, display_path, prefix, rel)
                else:
                    self._convert_file(source, dest_dir, display_path, ext)

    def _convert_zip(self, source: Path, dest_dir: Path, display_path: str, prefix: str, rel: Path) -> None:
        zip_out = dest_dir / source.name
        digest = HashManifest.digest(source)
        if (
            not self.settings.force
            and zip_out.is_dir()
            and digest
            and digest == self.manifest.old_hash(display_path)
        ):
            print(f"== {display_path}  (archive unchanged, skipped)")
            self.report.record_skipped(f"{display_path} (archive unchanged)")
            self.manifest.record(display_path, digest)
            return
        print(f"-> {display_path}  (extracting)")
        shutil.rmtree(zip_out, ignore_errors=True)
        zip_out.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            extraction = extract_zip_safe(source, tmp)
            if extraction.ok:
                failures_before = len(self.report.failed)
                self._walk(tmp, zip_out, f"{prefix}{rel.as_posix()}/")
                if len(self.report.failed) == failures_before:
                    self.manifest.record(display_path, digest)
                else:
                    issue = ConversionIssue(ConversionErrorCode.ARCHIVE_CHILD_FAILURE, "archive contains failed conversions")
                    self.report.record_failed(display_path, issue)
                    print(f"   !! archive contains failed conversions -- will retry next run: {display_path}")
            else:
                issue = extraction.issue or ConversionIssue(ConversionErrorCode.ARCHIVE_EXTRACTION_FAILED, "unzip failed")
                shutil.rmtree(zip_out, ignore_errors=True)
                print(f"   !! {issue.render()} -- will retry next run: {display_path}")
                self.report.record_failed(display_path, issue)

    def _convert_file(self, source: Path, dest_dir: Path, display_path: str, ext: str) -> None:
        dest = dest_dir / f"{source.name}.md"
        tmpdest = dest_dir / f".{source.name}.md.partial"
        digest = HashManifest.digest(source)
        if (
            not self.settings.force
            and dest.exists()
            and dest.stat().st_size > 0
            and digest
            and digest == self.manifest.old_hash(display_path)
        ):
            print(f"== {display_path}  (unchanged, skipped)")
            self.report.record_skipped(f"{display_path} (unchanged)")
            self.manifest.record(display_path, digest)
            return
        print(f"-> {display_path}")
        tmpdest.unlink(missing_ok=True)
        result = self.registry.convert(source, tmpdest, ext)
        if result.success:
            if result.produced:
                if tmpdest.exists() and tmpdest.stat().st_size > 0:
                    tmpdest.replace(dest)
                    self.report.record_converted(display_path)
                    self.manifest.record(display_path, digest)
                else:
                    tmpdest.unlink(missing_ok=True)
                    issue = ConversionIssue(ConversionErrorCode.EMPTY_OUTPUT, "empty output")
                    self.report.record_failed(display_path, issue)
                    print(f"   !! empty output -- removed (will retry next run): {source.name}")
            else:
                self.report.record_skipped(f"{display_path} (unsupported .{ext})")
        else:
            tmpdest.unlink(missing_ok=True)
            reason = result.reason or "conversion failed"
            self.report.record_failed(display_path, result.issue)
            print(f"   !! {reason} -- removed (will retry next run): {source.name}")

    def _print_preflight_warnings(self, source_exts: set[str]) -> None:
        capabilities = [CAPABILITY_BY_EXT[ext] for ext in sorted(source_exts) if ext in CAPABILITY_BY_EXT]
        required_tools = sorted({tool for capability in capabilities for tool in capability.required_tools})
        optional_tools = sorted({tool for capability in capabilities for tool in capability.optional_tools} - set(required_tools))
        missing = self.tools.warn_missing(required_tools)
        if missing:
            print(f"(heads up) required tools not found for this corpus: {' '.join(missing)}", file=os.sys.stderr)
            print("           related files may fail. If unexpected, activate your venv:", file=os.sys.stderr)
            print("           source ~/md-convert-env/bin/activate", file=os.sys.stderr)
            print(file=os.sys.stderr)
        optional_missing = self.tools.warn_missing(optional_tools)
        if optional_missing:
            print(f"(heads up) optional helpers not found for this corpus: {' '.join(optional_missing)}", file=os.sys.stderr)
            print("           conversion will continue, but metadata, rendering, OCR, or design detail may be reduced.", file=os.sys.stderr)
            print(file=os.sys.stderr)

    def _scan_extensions(self, src: Path) -> set[str]:
        exts: set[str] = set()
        for current, dirs, files in os.walk(src):
            dirs[:] = sorted(dir_name for dir_name in dirs if not self._is_pruned_name(dir_name))
            for file_name in files:
                if self._is_pruned_name(file_name):
                    continue
                source = Path(current) / file_name
                if source.is_symlink() or not source.is_file():
                    continue
                exts.add(extension_for(source.name))
        return exts

    @staticmethod
    def _is_pruned_name(name: str) -> bool:
        return name.startswith(".") or name == "__MACOSX" or name.startswith("._")


def extension_for(name: str) -> str:
    path = Path(name)
    if path.suffix:
        return path.suffix[1:].lower()
    return name.lower()
