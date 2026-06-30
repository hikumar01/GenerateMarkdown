from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DEFAULT_RENDER_DENSITY, DEFAULT_WHISPER_LANG, DEFAULT_WHISPER_MODEL, Settings
from .core import MarkdownConverter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch-convert a mixed-format project folder to Markdown.")
    parser.add_argument("--force", action="store_true", help="reconvert every supported file, ignoring the content-hash manifest")
    parser.add_argument("--whisper-model", help=f"mlx-whisper model name; defaults to WHISPER_MODEL or {DEFAULT_WHISPER_MODEL}")
    parser.add_argument("--whisper-lang", help=f"spoken language for transcription; defaults to WHISPER_LANG or {DEFAULT_WHISPER_LANG}; use an empty value to omit")
    parser.add_argument("--render-density", help=f"ImageMagick/Ghostscript render density; defaults to RENDER_DENSITY or {DEFAULT_RENDER_DENSITY}")
    parser.add_argument("src", help="input folder")
    parser.add_argument("out", help="output folder")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    src = Path(args.src).expanduser()
    out = Path(args.out).expanduser()
    if not src.is_dir():
        print(f"ERROR: input folder not found: {src}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    src_abs = src.resolve()
    out_abs = out.resolve()
    if out_abs == src_abs or src_abs in out_abs.parents:
        print(f"ERROR: output ({out}) is inside input ({src}). Choose a separate output folder.", file=sys.stderr)
        return 1
    settings = Settings.from_env(
        src_abs,
        out_abs,
        force=args.force,
        whisper_model=args.whisper_model,
        whisper_lang=args.whisper_lang,
        render_density=args.render_density,
    )
    return MarkdownConverter(settings).run()
