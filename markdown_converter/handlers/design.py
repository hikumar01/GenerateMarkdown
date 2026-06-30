from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from ..archive import extract_zip_safe
from ..capabilities import ConverterCapability
from ..errors import ConversionErrorCode, ConversionIssue
from ..markdown import fenced, image_link, md_escape
from ..package_extraction import StructuredPackageExtractor
from ..results import ConverterResult

PACKAGE_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
RAW_SNIPPET_EXTS = {".json", ".agc", ".txt", ".xml", ".svg"}
HIGH_FIDELITY_EXPORT_EXTS = {".pdf", ".svg", ".png", ".jpg", ".jpeg", ".html", ".htm"}


class DesignHandlerMixin:
    def _package(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        kind = capability.kind_by_ext.get(ext, "Design")
        dest_dir = dest.parent
        shutil.copy2(source, dest_dir / source.name)
        asset_rel = f"{source.name}.assets"
        asset_dir = dest_dir / asset_rel
        package_asset_dir = asset_dir / "package"
        parts = [
            f"# {source.name}\n",
            f"_{kind} design/package file. This Markdown includes every rendered page/frame available locally, package image assets, package contents, and text snippets when the file is zip-readable._\n",
        ]
        if self._render_pages(source, asset_dir):
            parts.append(self._rendered_pages_markdown(asset_dir, asset_rel, source.name))
        metadata = self._file_metadata(source)
        if metadata:
            parts.append(metadata)
        parts.append(design_alternatives_markdown(source, kind))
        if not zipfile.is_zipfile(source):
            parts.append("## Local conversion note\n\n_This file is not a readable zip package here. Export it from the source app as PDF, PNG, SVG, or HTML for full Markdown conversion._\n")
            dest.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
            return ConverterResult()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            extraction = extract_zip_safe(source, tmp)
            if not extraction.ok:
                issue = extraction.issue or ConversionIssue(ConversionErrorCode.PACKAGE_EXTRACTION_FAILED, "package extraction failed")
                return ConverterResult(success=False, produced=False, issue=issue)
            parts.append("## Package contents\n")
            for name in zip_inventory(source)[:200]:
                parts.append(f"- {md_escape(name, limit=500)}")
            parts.append("")
            image_files = sorted(path for path in tmp.rglob("*") if path.is_file() and path.suffix.lower() in PACKAGE_IMAGE_EXTS)
            if image_files:
                parts.append(f"## Package image assets ({len(image_files)})\n")
                for image_file in image_files:
                    rel = image_file.relative_to(tmp)
                    target = package_asset_dir / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(image_file, target)
                    rel_posix = rel.as_posix()
                    parts.append(image_link(rel_posix, f"{asset_rel}/package/{rel_posix}"))
                    parts.append("")
            parts.append(StructuredPackageExtractor(tmp, kind).render_markdown().rstrip())
            parts.append("")
            parts.append("## Raw readable snippets\n")
            snippet_files = sorted(path for path in tmp.rglob("*") if path.is_file() and path.suffix.lower() in RAW_SNIPPET_EXTS)[:20]
            if snippet_files:
                for text_file in snippet_files:
                    rel = text_file.relative_to(tmp).as_posix()
                    snippet = first_lines(text_file, 80)
                    parts.append(f"### {rel}\n")
                    parts.append(fenced(snippet, "text"))
            else:
                parts.append("_No text-like files were found inside the package._\n")
        dest.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        return ConverterResult()

    def _psd_layers(self, source: Path) -> str:
        try:
            from psd_tools import PSDImage
        except Exception:
            return "## Photoshop layer inventory\n\n_Install the optional design dependency (`pip install '.[design]'`) to extract PSD layer names and basic layer geometry locally._\n"
        try:
            psd = PSDImage.open(source)
            lines = ["## Photoshop layer inventory\n", f"- Size: {psd.width} x {psd.height} px"]
            layer_lines = list(psd_layer_lines(psd))
            lines.append(f"- Layers listed: {len(layer_lines)}")
            if layer_lines:
                lines.extend(["", "### Layers"])
                lines.extend(layer_lines)
            else:
                lines.append("- No layers were exposed by psd-tools")
            return "\n".join(lines).rstrip() + "\n"
        except Exception as exc:
            return f"## Photoshop layer inventory\n\n_Could not inspect PSD layers: {exc}_\n"


def zip_inventory(source: Path) -> list[str]:
    try:
        with zipfile.ZipFile(source) as archive:
            return archive.namelist()
    except Exception:
        return []


def first_lines(path: Path, count: int) -> str:
    lines: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= count:
                    break
                lines.append(line.rstrip("\n"))
    except OSError:
        return ""
    return "\n".join(lines)


def design_alternatives_markdown(source: Path, kind: str) -> str:
    parts = [
        "## Best-fidelity alternatives\n",
        f"For {kind} files, the most reliable readable Markdown comes from a companion export made by the source app:",
        "- PDF for full-page review and text extraction",
        "- SVG for vector structure and labels",
        "- PNG/JPG for visual review",
        "- HTML when the design tool can export browsable specs",
        "",
    ]
    companions = companion_exports(source)
    if companions:
        parts.append("Detected companion exports with the same basename:")
        parts.extend(f"- {md_escape(path.name)}" for path in companions)
        parts.append("")
    else:
        parts.append("_No same-basename PDF/SVG/PNG/JPG/HTML export was found next to this source file._\n")
    return "\n".join(parts).rstrip() + "\n"


def companion_exports(source: Path) -> list[Path]:
    try:
        return sorted(
            path
            for path in source.parent.iterdir()
            if path.is_file() and path != source and path.stem == source.stem and path.suffix.lower() in HIGH_FIDELITY_EXPORT_EXTS
        )
    except OSError:
        return []


def psd_layer_lines(psd: object, limit: int = 200) -> list[str]:
    lines: list[str] = []

    def walk(container: object, depth: int) -> None:
        if len(lines) >= limit:
            return
        try:
            children = list(container)  # type: ignore[arg-type]
        except TypeError:
            return
        for layer in children:
            if len(lines) >= limit:
                lines.append(f"- ... truncated after {limit} layers")
                return
            name = md_escape(str(getattr(layer, "name", "<unnamed>") or "<unnamed>"), limit=200)
            visible = getattr(layer, "visible", None)
            visibility = "visible" if visible is True else "hidden" if visible is False else "visibility unknown"
            bbox = getattr(layer, "bbox", None)
            kind = type(layer).__name__
            indent = "  " * depth
            suffix = f", bbox={bbox}" if bbox else ""
            lines.append(f"{indent}- {name} ({kind}, {visibility}{suffix})")
            walk(layer, depth + 1)

    walk(psd, 0)
    return lines