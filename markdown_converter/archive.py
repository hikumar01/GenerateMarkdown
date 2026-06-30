from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .errors import ConversionErrorCode, ConversionIssue

MAX_ARCHIVE_MEMBERS = 10_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class ArchiveExtractionResult:
    ok: bool
    issue: ConversionIssue | None = None
    extracted_files: int = 0
    skipped_files: int = 0
    total_uncompressed_bytes: int = 0


def extract_zip_safe(source: Path, target: Path) -> ArchiveExtractionResult:
    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                return _failed(
                    ConversionErrorCode.UNSAFE_ARCHIVE,
                    "archive has too many entries",
                    f"{len(members)} entries; limit is {MAX_ARCHIVE_MEMBERS}",
                )
            total_size = sum(max(member.file_size, 0) for member in members)
            if total_size > MAX_UNCOMPRESSED_BYTES:
                return _failed(
                    ConversionErrorCode.UNSAFE_ARCHIVE,
                    "archive expands beyond the safety limit",
                    f"{total_size} bytes; limit is {MAX_UNCOMPRESSED_BYTES}",
                )
            target_resolved = target.resolve()
            for member in members:
                if _should_skip(member.filename):
                    continue
                issue = _validate_member(member, target, target_resolved)
                if issue:
                    return ArchiveExtractionResult(False, issue, total_uncompressed_bytes=total_size)
            extracted = 0
            skipped = 0
            for member in members:
                if _should_skip(member.filename):
                    skipped += 1
                    continue
                archive.extract(member, target)
                if not member.is_dir():
                    extracted += 1
            return ArchiveExtractionResult(True, extracted_files=extracted, skipped_files=skipped, total_uncompressed_bytes=total_size)
    except zipfile.BadZipFile:
        return _failed(ConversionErrorCode.ARCHIVE_EXTRACTION_FAILED, "not a readable zip archive")
    except RuntimeError as exc:
        return _failed(ConversionErrorCode.ARCHIVE_EXTRACTION_FAILED, "could not extract archive", str(exc))
    except OSError as exc:
        return _failed(ConversionErrorCode.ARCHIVE_EXTRACTION_FAILED, "could not extract archive", str(exc))


def safe_extract_zip(source: Path, target: Path) -> bool:
    return extract_zip_safe(source, target).ok


def _validate_member(member: zipfile.ZipInfo, target: Path, target_resolved: Path) -> ConversionIssue | None:
    if member.flag_bits & 0x1:
        return ConversionIssue(ConversionErrorCode.UNSAFE_ARCHIVE, "archive contains encrypted entries", member.filename)
    if _is_symlink(member):
        return ConversionIssue(ConversionErrorCode.UNSAFE_ARCHIVE, "archive contains symlink entries", member.filename)
    path = PurePosixPath(member.filename)
    if path.is_absolute() or ".." in path.parts:
        return ConversionIssue(ConversionErrorCode.UNSAFE_ARCHIVE, "archive contains an unsafe path", member.filename)
    destination = (target / member.filename).resolve()
    if target_resolved != destination and target_resolved not in destination.parents:
        return ConversionIssue(ConversionErrorCode.UNSAFE_ARCHIVE, "archive escapes the extraction directory", member.filename)
    return None


def _is_symlink(member: zipfile.ZipInfo) -> bool:
    return (member.external_attr >> 16) & 0o170000 == 0o120000


def _should_skip(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return any(part == "__MACOSX" or part == ".DS_Store" or part.startswith("._") for part in parts)


def _failed(code: ConversionErrorCode, message: str, detail: str = "") -> ArchiveExtractionResult:
    return ArchiveExtractionResult(False, ConversionIssue(code, message, detail))