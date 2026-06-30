from __future__ import annotations

import json
import shutil
from configparser import ConfigParser, Error as ConfigParserError
from pathlib import Path
from urllib.parse import urlparse

from ..capabilities import ConverterCapability
from ..markdown import fenced, md_escape
from ..results import ConverterResult


class TextHandlerMixin:
    def _json(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        raw = source.read_text(encoding="utf-8-sig", errors="replace")
        parts = [f"# {source.name}\n", "## JSON summary\n"]
        try:
            data = json.loads(raw)
            body = json.dumps(data, indent=2, ensure_ascii=False)
            parts.append(json_summary(data))
            parts.append("## Formatted JSON\n")
        except Exception:
            body = raw
            parts.append("- Status: invalid JSON; raw text preserved for searchability\n")
            parts.append("## Raw contents\n")
        parts.append(fenced(body, "json"))
        dest.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        return ConverterResult()

    def _url(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        raw = source.read_text(encoding="utf-8-sig", errors="replace")
        url, fields = parse_url_shortcut(raw)
        parts = [f"# {source.stem}\n"]
        if url:
            parsed = urlparse(url)
            parts.append(f"[{url}]({url})\n")
            if parsed.scheme or parsed.netloc:
                parts.append("## Link metadata\n")
                if parsed.scheme:
                    parts.append(f"- Scheme: {md_escape(parsed.scheme)}")
                if parsed.netloc:
                    parts.append(f"- Host: {md_escape(parsed.netloc)}")
                parts.append("")
        else:
            parts.append("_No URL field found; raw contents are preserved below._\n")
        if fields:
            parts.append("## Shortcut fields\n")
            for key, value in fields.items():
                if key.lower() != "url":
                    parts.append(f"- {md_escape(key)}: {md_escape(value, limit=500)}")
            parts.append("")
        parts.append("## Raw shortcut\n")
        parts.append(fenced(raw, "ini"))
        dest.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        return ConverterResult()

    def _text(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        if ext in {"md", "markdown"}:
            shutil.copy2(source, dest)
            return ConverterResult()
        body = source.read_text(encoding="utf-8-sig", errors="replace")
        parts = [f"# {source.name}\n", "## Text\n", fenced(body, "text")]
        dest.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        return ConverterResult()


def json_summary(data: object) -> str:
    if isinstance(data, dict):
        keys = list(data.keys())
        preview = ", ".join(md_escape(str(key), limit=80) for key in keys[:20])
        suffix = "..." if len(keys) > 20 else ""
        return f"- Status: valid JSON\n- Top level: object\n- Keys: {len(keys)}\n- Key preview: {preview}{suffix}\n"
    if isinstance(data, list):
        return f"- Status: valid JSON\n- Top level: array\n- Items: {len(data)}\n"
    return f"- Status: valid JSON\n- Top level: {type(data).__name__}\n"


def parse_url_shortcut(raw: str) -> tuple[str, dict[str, str]]:
    parser = ConfigParser(interpolation=None)
    fields: dict[str, str] = {}
    try:
        parser.read_string(raw)
        if parser.has_section("InternetShortcut"):
            fields = {key: value for key, value in parser.items("InternetShortcut")}
    except ConfigParserError:
        fields = {}
    url = fields.get("url", "")
    if not url:
        for line in raw.splitlines():
            if line.strip().lower().startswith("url="):
                url = line.split("=", 1)[1].strip().strip("\r")
                fields.setdefault("url", url)
                break
    return url, fields