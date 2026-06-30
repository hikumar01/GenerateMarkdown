from __future__ import annotations

from pathlib import Path

from .capabilities import CAPABILITY_BY_EXT
from .config import Settings
from .errors import ConversionErrorCode
from .handlers.design import DesignHandlerMixin
from .handlers.documents import DocumentHandlerMixin
from .handlers.media import MediaHandlerMixin
from .handlers.text import TextHandlerMixin
from .handlers.visuals import VisualHandlerMixin
from .results import ConverterResult
from .tools import ToolRunner


class ConverterRegistry(DocumentHandlerMixin, TextHandlerMixin, DesignHandlerMixin, VisualHandlerMixin, MediaHandlerMixin):
    def __init__(self, settings: Settings, tools: ToolRunner) -> None:
        self.settings = settings
        self.tools = tools

    def convert(self, source: Path, dest: Path, ext: str) -> ConverterResult:
        try:
            capability = CAPABILITY_BY_EXT.get(ext)
            if capability and capability.handler != "_archive":
                handler = getattr(self, capability.handler)
                return handler(source, dest, ext, capability)
            return ConverterResult.skipped()
        except Exception as exc:
            return ConverterResult.failed(ConversionErrorCode.UNEXPECTED_ERROR, str(exc) or "conversion failed")