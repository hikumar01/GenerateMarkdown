from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


def md_escape(text: object, *, limit: int | None = None) -> str:
    value = str(text).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    value = re.sub(r"\s+", " ", value).strip().replace("`", "'")
    if limit is not None and len(value) > limit:
        value = value[: max(0, limit - 3)].rstrip() + "..."
    return value


def fenced(code: str, language: str = "text") -> str:
    return f"```{language}\n{code.rstrip()}\n```\n"


def image_link(alt: str, target: str) -> str:
    return f"![{alt}](<{target}>)"


def bullet_metadata(lines: Iterable[str], key_pattern: str = r"^([^:]+):\s*(.*)$") -> str:
    out = []
    pattern = re.compile(key_pattern)
    for line in lines:
        match = pattern.match(line.strip())
        if match:
            key = md_escape(match.group(1))
            value = md_escape(match.group(2), limit=500)
            out.append(f"- **{key}:** {value}")
        elif line.strip():
            out.append(f"- {md_escape(line, limit=500)}")
    return "\n".join(out) + ("\n" if out else "")


def posix_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
