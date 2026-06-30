from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .errors import ConversionIssue


@dataclass(frozen=True)
class FailedItem:
    path: str
    issue: ConversionIssue | None = None

    def render(self) -> str:
        if self.issue:
            return f"{self.path} ({self.issue.render()})"
        return self.path

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"path": self.path}
        if self.issue:
            data["issue"] = self.issue.as_dict()
        return data


@dataclass
class ConversionReport:
    converted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[FailedItem] = field(default_factory=list)

    def record_converted(self, item: str) -> None:
        self.converted.append(item)

    def record_skipped(self, item: str) -> None:
        self.skipped.append(item)

    def record_failed(self, item: str, issue: ConversionIssue | None = None) -> None:
        self.failed.append(FailedItem(item, issue))

    def render(self, src: Path, out: Path, force: bool) -> str:
        lines = [
            "================= Conversion report =================",
            f"When:    {datetime.now().ctime()}",
            f"Source:  {src}",
            f"Output:  {out}",
            f"Mode:    {'force rebuild' if force else 'content-hash'}",
            "",
            f"Converted: {len(self.converted)}",
            f"Skipped:   {len(self.skipped)}",
            f"Failed:    {len(self.failed)}",
        ]
        if self.skipped:
            lines.extend(["", f"Skipped files ({len(self.skipped)}):"])
            lines.extend(f"  == {item}" for item in self.skipped)
        if self.failed:
            lines.extend(["", f"Failed files ({len(self.failed)}):"])
            lines.extend(f"  !! {item.render()}" for item in self.failed)
        return "\n".join(lines) + "\n"

    def as_dict(self, src: Path, out: Path, force: bool) -> dict[str, object]:
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": str(src),
            "output": str(out),
            "mode": "force rebuild" if force else "content-hash",
            "counts": {
                "converted": len(self.converted),
                "skipped": len(self.skipped),
                "failed": len(self.failed),
            },
            "converted": self.converted,
            "skipped": self.skipped,
            "failed": [item.as_dict() for item in self.failed],
        }

    def write_json(self, path: Path, src: Path, out: Path, force: bool) -> None:
        path.write_text(json.dumps(self.as_dict(src, out, force), indent=2) + "\n", encoding="utf-8")
