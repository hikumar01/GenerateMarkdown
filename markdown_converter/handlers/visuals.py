from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from ..capabilities import ConverterCapability
from ..markdown import bullet_metadata, image_link, md_escape
from ..results import ConverterResult
from .design import design_alternatives_markdown


class VisualHandlerMixin:
    def _image(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        dest_dir = dest.parent
        shutil.copy2(source, dest_dir / source.name)
        parts = [f"# {source.name}\n", image_link(source.name, source.name), ""]
        details = self._image_details(source)
        if details:
            parts.append(details)
        photo = self._photo_metadata(source)
        if photo:
            parts.append("## Photo metadata\n")
            parts.append(photo)
        parts.append("## Text (OCR)\n")
        parts.append(self._ocr(source))
        dest.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        return ConverterResult()

    def _visual_markdown(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        dest_dir = dest.parent
        shutil.copy2(source, dest_dir / source.name)
        asset_rel = f"{source.name}.assets"
        asset_dir = dest_dir / asset_rel
        note = capability.note_by_ext.get(ext, capability.description)
        parts = [f"# {source.name}\n", f"_{note}_\n"]
        if self._render_pages(source, asset_dir):
            metadata = self._file_metadata(source)
            if metadata:
                parts.append(metadata)
            parts.append(self._rendered_pages_markdown(asset_dir, asset_rel, source.name))
        else:
            metadata = self._file_metadata(source)
            if metadata:
                parts.append(metadata)
            parts.append("_No pages/frames could be rendered locally. Install ImageMagick/Ghostscript (`brew install imagemagick ghostscript`) or export this file to PDF/PNG/SVG, then rerun._\n")
        if ext == "psd":
            parts.append(self._psd_layers(source))
            parts.append(design_alternatives_markdown(source, "Photoshop"))
        dest.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        return ConverterResult()

    def _onenote(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        shutil.copy2(source, dest.parent / source.name)
        parts = [
            f"# {source.name}\n",
            "_Microsoft OneNote `.one`/`.onetoc2` files are proprietary binary notebook containers, and this script does not have a reliable free local reader for their page text._\n",
        ]
        metadata = self._file_metadata(source)
        if metadata:
            parts.append(metadata)
        parts.append("## How to make it readable\n")
        parts.append("Export the notebook or section from OneNote as PDF, DOCX, or HTML, put that exported file in the input folder, then rerun this converter. The exported file will be converted to searchable Markdown by the existing document handlers.\n")
        dest.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        return ConverterResult()

    def _svg(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        dest_dir = dest.parent
        shutil.copy2(source, dest_dir / source.name)
        parts = [f"# {source.name}\n", image_link(source.name, source.name), ""]
        rendered_name = f"{source.name}.png"
        if self.tools.exists("rsvg-convert"):
            result = self.tools.run(["rsvg-convert", source, "-o", dest_dir / rendered_name], quiet=True)
            if result.ok and (dest_dir / rendered_name).exists():
                parts.append(image_link(f"{source.name} rendered", rendered_name))
                parts.append("")
        parts.append("## Text labels\n")
        parts.append(self._svg_labels(source))
        dest.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        return ConverterResult()

    def _font(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        try:
            from fontTools.ttLib import TTFont

            font = TTFont(str(source), fontNumber=0, lazy=True)

            def name(item: int) -> str:
                try:
                    return font["name"].getDebugName(item) or ""
                except Exception:
                    return ""

            full = name(4) or name(1) or source.name
            rows = [
                ("File", source.name),
                ("Family", name(1)),
                ("Style", name(2)),
                ("Full name", name(4)),
                ("Version", name(5)),
                ("Designer", name(9)),
            ]
            if "maxp" in font:
                rows.append(("Glyph count", str(font["maxp"].numGlyphs)))
            if "head" in font:
                rows.append(("Units per em", str(font["head"].unitsPerEm)))
            lines = [f"# Font: {full}\n", "| Field | Value |", "|---|---|"]
            for key, value in rows:
                if value:
                    lines.append(f"| {key} | {md_escape(value)} |")
            lines.append("\n_Note: font files contain glyph outlines, not document text; this is metadata only._\n")
            font.close()
            dest.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:
            dest.write_text(f"# {source.name}\n\n_Could not read font metadata: {exc}_\n", encoding="utf-8")
        return ConverterResult()

    def _render_pages(self, source: Path, asset_dir: Path) -> bool:
        if asset_dir.exists():
            shutil.rmtree(asset_dir)
        asset_dir.mkdir(parents=True, exist_ok=True)
        if self.tools.exists("magick"):
            self.tools.run(["magick", "-density", self.settings.render_density, source, "-auto-orient", asset_dir / "page-%03d.png"], quiet=True)
            if rendered_pages(asset_dir):
                return True
        for page in asset_dir.glob("page-*.png"):
            page.unlink(missing_ok=True)
        if self.tools.exists("convert"):
            self.tools.run(["convert", "-density", self.settings.render_density, source, "-auto-orient", asset_dir / "page-%03d.png"], quiet=True)
            if rendered_pages(asset_dir):
                return True
        for page in asset_dir.glob("page-*.png"):
            page.unlink(missing_ok=True)
        if self.tools.exists("sips"):
            result = self.tools.run(["sips", "-s", "format", "png", source, "--out", asset_dir / "page-000.png"], quiet=True)
            if result.ok and (asset_dir / "page-000.png").stat().st_size > 0:
                return True
        shutil.rmtree(asset_dir, ignore_errors=True)
        return False

    def _rendered_pages_markdown(self, asset_dir: Path, asset_rel: str, fname: str) -> str:
        pages = rendered_pages(asset_dir)
        parts = [f"## Rendered pages / frames ({len(pages)})\n"]
        for index, page in enumerate(pages, 1):
            parts.append(f"### Render {index}\n")
            parts.append(image_link(f"{fname} render {index}", f"{asset_rel}/{page.name}"))
            parts.append("")
            details = self._image_details(page)
            if details:
                parts.append(details)
            parts.append("#### Text (OCR)\n")
            parts.append(self._ocr(page))
        return "\n".join(parts).rstrip() + "\n"

    def _image_details(self, image: Path) -> str:
        if self.tools.exists("sips"):
            result = self.tools.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", "-g", "format", image])
            if result.ok:
                width = height = fmt = ""
                for line in result.stdout.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("pixelWidth:"):
                        width = stripped.split(":", 1)[1].strip()
                    elif stripped.startswith("pixelHeight:"):
                        height = stripped.split(":", 1)[1].strip()
                    elif stripped.startswith("format:"):
                        fmt = stripped.split(":", 1)[1].strip()
                if width:
                    return f"**Image:** {width} x {height} px, {fmt}\n"
        if self.tools.exists("identify"):
            result = self.tools.run(["identify", "-format", "**Image:** %w x %h px, %m\\n", image])
            if result.ok and result.stdout.strip():
                return result.stdout.strip() + "\n"
        return ""

    def _photo_metadata(self, source: Path) -> str:
        if not self.tools.exists("exiftool"):
            return ""
        tags = ["-s", "-DateTimeOriginal", "-CreateDate", "-Make", "-Model", "-LensModel", "-GPSPosition", "-ISO", "-FNumber", "-ExposureTime", "-FocalLength", "-ImageDescription"]
        result = self.tools.run(["exiftool", *tags, source])
        return bullet_metadata(result.stdout.splitlines(), r"^([A-Za-z0-9]+)\s*:\s*(.*)$") if result.ok and result.stdout.strip() else ""

    def _file_metadata(self, source: Path) -> str:
        if not self.tools.exists("exiftool"):
            return ""
        tags = ["-s", "-FileType", "-MIMEType", "-ImageWidth", "-ImageHeight", "-ColorMode", "-ColorSpace", "-ProfileDescription", "-Title", "-Description", "-Creator", "-Author", "-CreateDate", "-ModifyDate", "-DateTimeOriginal"]
        result = self.tools.run(["exiftool", *tags, source])
        if not result.ok or not result.stdout.strip():
            return ""
        return "## File metadata\n\n" + bullet_metadata(result.stdout.splitlines(), r"^([A-Za-z0-9_:-]+)\s*:\s*(.*)$")

    def _ocr(self, image: Path) -> str:
        if not self.tools.exists("tesseract"):
            return "_tesseract not installed; run: brew install tesseract_\n"
        result = self.tools.run(["tesseract", image, "stdout"])
        if result.ok and result.stdout.strip():
            return result.stdout.rstrip() + "\n"
        return "_OCR produced no text._\n"

    @staticmethod
    def _svg_labels(source: Path) -> str:
        texts: list[str] = []
        try:
            for element in ET.parse(source).iter():
                tag = element.tag.split("}")[-1].lower()
                if tag in ("text", "tspan", "title", "desc") and element.text and element.text.strip():
                    texts.append(element.text.strip())
        except Exception as exc:
            return f"_Could not parse SVG: {exc}_\n"
        if not texts:
            return "_No text labels in this vector graphic._\n"
        return "\n".join(f"- {md_escape(text, limit=500)}" for text in texts) + "\n"


def rendered_pages(asset_dir: Path) -> list[Path]:
    return sorted(path for path in asset_dir.glob("page-*.png") if path.is_file() and path.stat().st_size > 0)