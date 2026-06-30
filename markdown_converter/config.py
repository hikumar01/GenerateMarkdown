from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_WHISPER_LANG = "en"
DEFAULT_RENDER_DENSITY = "200"


@dataclass(frozen=True)
class Settings:
    src: Path
    out: Path
    force: bool
    whisper_model: str
    whisper_lang: str
    render_density: str

    @classmethod
    def from_env(
        cls,
        src: Path,
        out: Path,
        *,
        force: bool = False,
        whisper_model: str | None = None,
        whisper_lang: str | None = None,
        render_density: str | None = None,
    ) -> "Settings":
        return cls(
            src=src,
            out=out,
            force=force or env_flag("FORCE"),
            whisper_model=whisper_model or os.environ.get("WHISPER_MODEL", DEFAULT_WHISPER_MODEL),
            whisper_lang=whisper_lang if whisper_lang is not None else os.environ.get("WHISPER_LANG", DEFAULT_WHISPER_LANG),
            render_density=render_density or os.environ.get("RENDER_DENSITY", DEFAULT_RENDER_DENSITY),
        )


def env_flag(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}
