from __future__ import annotations

import hashlib
from pathlib import Path


class HashManifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.old = self._read(path)
        self.new: dict[str, str] = {}

    def old_hash(self, display_path: str) -> str | None:
        return self.old.get(display_path)

    def record(self, display_path: str, digest: str | None) -> None:
        if digest:
            self.new[display_path] = digest

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.partial")
        with tmp.open("w", encoding="utf-8") as handle:
            for key, digest in self.new.items():
                handle.write(f"{key}\t{digest}\n")
        tmp.replace(self.path)

    @staticmethod
    def digest(path: Path) -> str | None:
        try:
            hasher = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError:
            return None

    @staticmethod
    def _read(path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        data: dict[str, str] = {}
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    key, sep, digest = line.rstrip("\n").partition("\t")
                    if sep and key and digest:
                        data[key] = digest
        except OSError:
            return {}
        return data
