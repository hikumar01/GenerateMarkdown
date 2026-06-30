from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConverterCapability:
    name: str
    extensions: frozenset[str]
    handler: str
    description: str
    required_tools: tuple[str, ...] = ()
    optional_tools: tuple[str, ...] = ()
    target_by_ext: Mapping[str, str] = field(default_factory=dict)
    kind_by_ext: Mapping[str, str] = field(default_factory=dict)
    note_by_ext: Mapping[str, str] = field(default_factory=dict)


MARKITDOWN_EXTS = frozenset({"pdf", "docx", "pptx", "xlsx", "xls", "html", "htm", "csv"})
LIBREOFFICE_TARGET_BY_EXT = {"xlsb": "xlsx", "doc": "docx", "ppt": "pptx"}
XLSM_EXTS = frozenset({"xlsm"})
RTF_EXTS = frozenset({"rtf"})
PAGES_EXTS = frozenset({"pages"})
JSON_EXTS = frozenset({"json"})
URL_EXTS = frozenset({"url"})
IMAGE_EXTS = frozenset({"jpg", "jpeg", "png"})
VISUAL_EXTS = frozenset({"tif", "tiff", "heic", "heif", "hei"})
VECTOR_EXTS = frozenset({"ai", "eps"})
PSD_EXTS = frozenset({"psd"})
DESIGN_PACKAGE_KIND_BY_EXT = {"xd": "Adobe XD", "fig": "Figma"}
ONENOTE_EXTS = frozenset({"one", "onetoc2"})
SVG_EXTS = frozenset({"svg"})
FONT_EXTS = frozenset({"otf", "ttf", "ttc"})
TEXT_EXTS = frozenset({"txt", "md", "markdown"})
MEDIA_EXTS = frozenset({"mp4", "mov", "m4v", "mkv", "avi", "webm", "mp3", "m4a", "wav", "aac", "flac"})
ARCHIVE_EXTS = frozenset({"zip"})

CAPABILITIES = (
    ConverterCapability(
        "markitdown-document",
        MARKITDOWN_EXTS,
        "_markitdown",
        "Documents converted through markitdown.",
        required_tools=("markitdown",),
    ),
    ConverterCapability(
        "xlsm-workbook",
        XLSM_EXTS,
        "_xlsm",
        "Macro-enabled workbook data converted as xlsx; macros are ignored.",
        required_tools=("markitdown",),
    ),
    ConverterCapability(
        "libreoffice-legacy-document",
        frozenset(LIBREOFFICE_TARGET_BY_EXT),
        "_libreoffice_then_markitdown",
        "Legacy Office formats converted by LibreOffice before markitdown.",
        required_tools=("soffice", "markitdown"),
        target_by_ext=LIBREOFFICE_TARGET_BY_EXT,
    ),
    ConverterCapability(
        "rtf-document",
        RTF_EXTS,
        "_rtf",
        "RTF converted by textutil to HTML before markitdown.",
        required_tools=("textutil", "markitdown"),
    ),
    ConverterCapability(
        "pages-document",
        PAGES_EXTS,
        "_pages",
        "Apple Pages converted from its embedded QuickLook preview PDF.",
        required_tools=("markitdown",),
    ),
    ConverterCapability("json", JSON_EXTS, "_json", "JSON preserved as searchable formatted Markdown."),
    ConverterCapability("url-shortcut", URL_EXTS, "_url", "Internet shortcut converted to a Markdown link plus metadata."),
    ConverterCapability(
        "raster-image",
        IMAGE_EXTS,
        "_image",
        "Raster image copied and embedded with metadata and OCR.",
        optional_tools=("sips", "identify", "exiftool", "tesseract"),
    ),
    ConverterCapability(
        "multi-frame-visual",
        VISUAL_EXTS,
        "_visual_markdown",
        "Visual file rendered into one PNG per page/frame when local tools expose them.",
        optional_tools=("magick", "convert", "sips", "exiftool", "tesseract"),
        note_by_ext={ext: "Rendered pages/frames for Markdown viewing, plus metadata and OCR." for ext in VISUAL_EXTS},
    ),
    ConverterCapability(
        "vector-art",
        VECTOR_EXTS,
        "_visual_markdown",
        "Vector art rendered into PNG pages/artboards when local tools expose them.",
        optional_tools=("magick", "convert", "ghostscript", "exiftool", "tesseract"),
        note_by_ext={ext: "Rendered vector-art pages/artboards plus metadata and OCR. Text converted to outlines may only be available through OCR." for ext in VECTOR_EXTS},
    ),
    ConverterCapability(
        "photoshop-document",
        PSD_EXTS,
        "_visual_markdown",
        "Photoshop document rendered and inspected with the best local tools available.",
        optional_tools=("magick", "convert", "sips", "exiftool", "tesseract", "python:psd_tools"),
        note_by_ext={"psd": "Rendered Photoshop composite/layer scenes plus metadata and OCR. Layer semantics are included when local tools expose them."},
    ),
    ConverterCapability(
        "design-package",
        frozenset(DESIGN_PACKAGE_KIND_BY_EXT),
        "_package",
        "Design package copied, rendered when possible, and inspected for readable package internals.",
        optional_tools=("magick", "convert", "sips", "exiftool", "tesseract"),
        kind_by_ext=DESIGN_PACKAGE_KIND_BY_EXT,
    ),
    ConverterCapability("onenote", ONENOTE_EXTS, "_onenote", "OneNote binary containers get a readable export-guidance note."),
    ConverterCapability(
        "svg",
        SVG_EXTS,
        "_svg",
        "SVG copied, embedded, optionally rendered, and inspected for text labels.",
        optional_tools=("rsvg-convert",),
    ),
    ConverterCapability("font", FONT_EXTS, "_font", "Font metadata extracted with fonttools when available."),
    ConverterCapability("text", TEXT_EXTS, "_text", "Plain text wrapped as Markdown; Markdown files are copied unchanged."),
    ConverterCapability(
        "media-transcription",
        MEDIA_EXTS,
        "_media",
        "Audio/video transcribed locally.",
        required_tools=("mlx_whisper",),
        optional_tools=("ffprobe",),
    ),
    ConverterCapability("zip-archive", ARCHIVE_EXTS, "_archive", "Zip archives are safely extracted and converted recursively."),
)

CAPABILITY_BY_EXT = {ext: capability for capability in CAPABILITIES for ext in capability.extensions}
SUPPORTED_SOURCE_EXTS = frozenset(CAPABILITY_BY_EXT)


def capability_for(ext: str) -> ConverterCapability | None:
    return CAPABILITY_BY_EXT.get(ext)