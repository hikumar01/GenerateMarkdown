from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from .markdown import md_escape

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_ITEMS = 250
STRING_KEYS = {
    "name",
    "title",
    "label",
    "text",
    "characters",
    "content",
    "description",
    "alt",
    "aria-label",
    "placeholder",
    "tooltip",
    "value",
    "string",
    "copy",
}
TYPE_KEYS = ("type", "_class", "class", "nodeType", "node_type", "kind", "role")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".heic", ".tif", ".tiff")


class StructuredPackageExtractor:
    def __init__(self, package_root: Path, kind: str) -> None:
        self.package_root = package_root
        self.kind = kind
        self.json_files = 0
        self.xml_files = 0
        self.text_files = 0
        self.design_text: OrderedDict[tuple[str, str, str], tuple[str, str, str]] = OrderedDict()
        self.named_objects: OrderedDict[tuple[str, str, str, str], tuple[str, str, str, str]] = OrderedDict()
        self.colors: OrderedDict[tuple[str, str, str], tuple[str, str, str]] = OrderedDict()
        self.asset_refs: OrderedDict[tuple[str, str, str], tuple[str, str, str]] = OrderedDict()
        self.json_errors: list[tuple[str, str]] = []

    def render_markdown(self) -> str:
        self._scan()
        parts = [
            "## Structured package extraction\n",
            f"- Package type: {self.kind}",
            f"- JSON-like files parsed: {self.json_files}",
            f"- XML/SVG files parsed: {self.xml_files}",
            f"- Text files sampled: {self.text_files}\n",
        ]
        parts.append(self._records("Design text strings", self.design_text, lambda item: f"- `{md_escape(item[0])}` _(source: {md_escape(item[1])}, path: {md_escape(item[2])})_"))
        parts.append(
            self._records(
                "Named objects, frames, and components",
                self.named_objects,
                lambda item: f"- `{md_escape(item[0])}`"
                + (f" [{md_escape(item[1])}]" if item[1] else "")
                + f" _(source: {md_escape(item[2])}, path: {md_escape(item[3])})_",
            )
        )
        parts.append(self._records("Colors", self.colors, lambda item: f"- `{md_escape(item[0])}` _(source: {md_escape(item[1])}, path: {md_escape(item[2])})_"))
        parts.append(
            self._records(
                "Asset references found in metadata",
                self.asset_refs,
                lambda item: f"- `{md_escape(item[0])}` _(source: {md_escape(item[1])}, path: {md_escape(item[2])})_",
            )
        )
        if self.json_errors:
            parts.append("### JSON parse warnings\n")
            for source, error in self.json_errors[:50]:
                parts.append(f"- `{md_escape(source)}`: {md_escape(error)}")
            parts.append("")
        return "\n".join(parts).rstrip() + "\n\n"

    def _scan(self) -> None:
        for current, _, files in os.walk(self.package_root):
            for filename in sorted(files):
                if filename == ".package-image-list":
                    continue
                path = Path(current) / filename
                source = self._rel(path)
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size > MAX_FILE_BYTES:
                    continue
                try:
                    raw = path.read_bytes()[: MAX_FILE_BYTES + 1]
                except OSError:
                    continue
                ext = path.suffix.lower()
                stripped = raw.lstrip()
                if stripped.startswith((b"{", b"[")):
                    try:
                        data = json.loads(raw.decode("utf-8-sig", errors="replace"))
                        self.json_files += 1
                        self._walk_json(data, source, [source])
                        continue
                    except Exception as exc:
                        self.json_errors.append((source, str(exc)))
                if ext in (".svg", ".xml"):
                    self._scan_xml(raw, source)
                elif ext in (".txt", ".md", ".csv"):
                    self._scan_text(raw, source)

    def _walk_json(self, obj: Any, source: str, parts: list[str | int]) -> None:
        if isinstance(obj, dict):
            typ = self._first_scalar(obj, TYPE_KEYS)
            name = ""
            for key, value in obj.items():
                if self._useful_string(key, value):
                    name = value
                    break
            if name:
                object_key = (self._clean(name), self._clean(typ), source, self._path_label(parts))
                self.named_objects.setdefault(object_key, object_key)
            color = self._color_from_dict(obj)
            if color:
                color_key = (color, source, self._path_label(parts))
                self.colors.setdefault(color_key, color_key)
            for key, value in obj.items():
                child_parts = parts + [str(key)]
                if self._useful_string(key, value):
                    text_key = (self._clean(value, 500), source, self._path_label(child_parts))
                    self.design_text.setdefault(text_key, text_key)
                if isinstance(value, str):
                    cleaned = self._clean(value, 1000)
                    lowered = cleaned.lower()
                    if lowered.endswith(IMAGE_EXTS) or any(ext + "?" in lowered for ext in IMAGE_EXTS):
                        asset_key = (cleaned, source, self._path_label(child_parts))
                        self.asset_refs.setdefault(asset_key, asset_key)
                    for match in re.findall(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?", cleaned):
                        color_key = (match.upper(), source, self._path_label(child_parts))
                        self.colors.setdefault(color_key, color_key)
                self._walk_json(value, source, child_parts)
        elif isinstance(obj, list):
            for index, value in enumerate(obj):
                self._walk_json(value, source, parts + [index])

    def _scan_xml(self, raw: bytes, source: str) -> None:
        try:
            tree = ET.fromstring(raw.decode("utf-8", errors="replace"))
        except Exception:
            return
        self.xml_files += 1
        for element in tree.iter():
            tag = element.tag.split("}")[-1].lower()
            text = self._clean(element.text or "", 500)
            if tag in ("text", "tspan", "title", "desc") and text:
                key = (text, source, tag)
                self.design_text.setdefault(key, key)
            for attr_key, attr_value in element.attrib.items():
                if self._useful_string(attr_key, attr_value):
                    key = (self._clean(attr_value, 500), source, f"@{attr_key}")
                    self.design_text.setdefault(key, key)

    def _scan_text(self, raw: bytes, source: str) -> None:
        self.text_files += 1
        text = raw.decode("utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines()[:200], 1):
            line = self._clean(line, 500)
            if line:
                key = (line, source, f"line {line_no}")
                self.design_text.setdefault(key, key)

    def _records(self, title: str, records: OrderedDict, formatter: Callable[[tuple], str]) -> str:
        lines = [f"### {title}\n"]
        if not records:
            lines.append("_None found._\n")
            return "\n".join(lines)
        for index, record in enumerate(records.values()):
            if index >= MAX_OUTPUT_ITEMS:
                lines.append(f"- _Output truncated after {MAX_OUTPUT_ITEMS} items._")
                break
            lines.append(formatter(record))
        lines.append("")
        return "\n".join(lines)

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.package_root).as_posix()

    @staticmethod
    def _clean(value: object, limit: int = 240) -> str:
        text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > limit:
            text = text[: limit - 3].rstrip() + "..."
        return text

    @staticmethod
    def _useful_string(key: object, value: object) -> bool:
        if not isinstance(value, str):
            return False
        text = StructuredPackageExtractor._clean(value, 2000)
        if not text or len(text) < 2:
            return False
        if text.startswith(("data:", "base64,")) or len(text) > 2000:
            return False
        key_l = str(key).lower()
        return key_l in STRING_KEYS or any(token in key_l for token in ("text", "name", "title", "label", "description", "character"))

    @staticmethod
    def _first_scalar(obj: dict[str, Any], keys: tuple[str, ...]) -> str:
        lower = {str(k).lower(): v for k, v in obj.items() if isinstance(v, (str, int, float, bool))}
        for key in keys:
            if key.lower() in lower:
                return str(lower[key.lower()])
        return ""

    @staticmethod
    def _path_label(parts: list[str | int]) -> str:
        out = []
        for part in parts:
            out.append(f"[{part}]" if isinstance(part, int) else str(part))
        return ".".join(out) or "$"

    @staticmethod
    def _color_from_dict(obj: dict[str, Any]) -> str:
        lower = {str(k).lower(): v for k, v in obj.items()}
        if not all(k in lower for k in ("r", "g", "b")):
            return ""
        try:
            vals = [float(lower[k]) for k in ("r", "g", "b")]
        except Exception:
            return ""
        if all(0 <= value <= 1 for value in vals):
            vals = [round(value * 255) for value in vals]
        elif all(0 <= value <= 255 for value in vals):
            vals = [round(value) for value in vals]
        else:
            return ""
        alpha = ""
        if "a" in lower:
            try:
                alpha_value = float(lower["a"])
                alpha = f", alpha {alpha_value:g}"
            except Exception:
                alpha = ""
        return "#%02X%02X%02X%s" % (vals[0], vals[1], vals[2], alpha)
