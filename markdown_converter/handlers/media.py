from __future__ import annotations

from pathlib import Path

from ..capabilities import ConverterCapability
from ..errors import ConversionErrorCode
from ..results import ConverterResult


class MediaHandlerMixin:
    def _media(self, source: Path, dest: Path, ext: str, capability: ConverterCapability) -> ConverterResult:
        out_dir = dest.parent
        if self.tools.exists("ffprobe"):
            result = self.tools.run(
                ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", source]
            )
            if result.ok and not result.stdout.strip():
                dest.write_text(f"# {source.name}\n\n_Silent video: no audio track to transcribe._\n", encoding="utf-8")
                print("   (no audio stream -> wrote stub)")
                return ConverterResult()
        args: list[str | Path] = ["mlx_whisper", source, "-f", "txt", "-o", out_dir, "--model", self.settings.whisper_model]
        if self.settings.whisper_lang:
            args.extend(["--language", self.settings.whisper_lang])
        result = self.tools.run(args, capture=False)
        transcript = out_dir / f"{source.stem}.txt"
        if result.ok and transcript.exists():
            transcript.replace(dest)
            return ConverterResult()
        return ConverterResult.failed(ConversionErrorCode.TRANSCRIPTION_FAILED, "transcription failed")