The project uses two kinds of external tools: **Python packages** and **system command-line tools**.

**Python Packages**
- `markitdown`  
  Converts PDF, DOCX, PPTX, XLS/XLSX, HTML, CSV to Markdown.

- `mlx-whisper`  
  Transcribes audio/video locally on Apple Silicon.

- `openai-whisper`  
  Optional Intel/non-MLX alternative if you choose that backend.

- `fonttools`  
  Reads font metadata from `.otf`, `.ttf`, `.ttc`.

- `psd-tools`  
  Optional design extra for PSD layer names, visibility, type, and geometry.

- `hatchling`  
  Build backend for packaging.

- `pytest`, `ruff`  
  Optional dev tools.

**System / CLI Tools**
- `ffmpeg` / `ffprobe`  
  Audio/video handling. `ffprobe` checks whether video has an audio stream.

- `tesseract`  
  OCR for images and rendered pages.

- `exiftool`  
  Photo/image/document metadata extraction.

- `librsvg` / `rsvg-convert`  
  Renders SVG to PNG.

- `ImageMagick` / `magick`  
  Renders HEIC/TIFF/AI/EPS/PSD and other visual formats into PNG pages/frames.

- `convert`  
  Older ImageMagick command fallback.

- `Ghostscript`  
  Used by ImageMagick for PDF/PostScript/EPS/AI rendering support.

- `LibreOffice` / `soffice`  
  Converts legacy Office formats like `.doc`, `.ppt`, `.xlsb` before Markdown conversion.

- macOS `textutil`  
  Converts RTF to HTML before Markdown conversion.

- macOS `sips`  
  Fallback image conversion and image details on macOS.

**Core Python Standard Library Used**
Not “external,” but important:
- `zipfile` for zip, `.pages`, `.xd`, `.fig` package inspection/extraction
- `json` for JSON formatting and package summaries
- `hashlib` for SHA-256 change detection
- `subprocess` for tool execution
- `xml.etree.ElementTree` for SVG text label extraction

So the major external runtime dependencies are: `markitdown`, `mlx-whisper`, `fonttools`, optional `psd-tools`, plus Homebrew tools like `ffmpeg`, `tesseract`, `exiftool`, `librsvg`, `imagemagick`, `ghostscript`, and `libreoffice`.

=======

Yes, some system tools can be replaced with public Python libraries, but not all replacements are equally good. The architecturally clean approach is: **replace tools where Python libraries are reliable, keep system tools where native applications/codecs/renderers are materially better.**

**Good Python Replacements**

| Current system tool | Python/public alternative | Recommendation |
|---|---|---|
| `exiftool` | `Pillow`, `pillow-heif`, `piexif`, `exifread` | Replace or make Python-first. Good enough for common image EXIF. |
| `tesseract` | `easyocr`, `paddleocr`, `keras-ocr` | Possible, but heavier. Keep optional unless OCR is core. |
| `ffprobe` | `ffmpeg-python`, `pymediainfo`, `av` / PyAV | Replace `ffprobe` for audio-stream detection if you want fewer CLI calls. |
| `librsvg` / `rsvg-convert` | `cairosvg` | Good candidate for SVG to PNG rendering. |
| macOS `sips` | `Pillow`, `pillow-heif`, `imageio` | Replace for image dimensions/basic conversion. |
| `textutil` for RTF | `striprtf`, `pypandoc`, `python-docx` does not handle RTF | `striprtf` can replace basic RTF text extraction, but not rich layout. |
| `LibreOffice` for `.doc` / `.ppt` / `.xlsb` | limited libraries: `antiword`, `python-pptx`, `pyxlsb`, `mammoth` | Partially replace. `.xlsb` can use `pyxlsb`; `.doc`/`.ppt` are harder. |
| `ImageMagick` / `convert` | `Pillow`, `pillow-heif`, `imageio`, `Wand` | Partial replacement only. Good for raster images, weaker for AI/EPS/PSD rendering. |
| `Ghostscript` | `PyMuPDF`, `pypdfium2`, `ghostscript` Python wrapper | For PDFs, yes. For EPS/AI through PostScript, native Ghostscript is still strongest. |

**Best Candidates To Replace First**

1. **`exiftool` → `Pillow` / `exifread`**
   
   This is the easiest win. You can extract common EXIF fields directly in Python.

   Tradeoff: ExifTool supports a much wider range of metadata formats. Python libraries cover common photo metadata well.

2. **`sips` → `Pillow` + `pillow-heif`**
   
   Good replacement for:
   - image dimensions
   - image format detection
   - HEIC/HEIF basic support
   - simple raster conversion

3. **`rsvg-convert` → `cairosvg`**
   
   Good replacement for SVG to PNG.

4. **`ffprobe` → `PyAV`**
   
   Good replacement for “does this media file have an audio stream?”

5. **`.xlsb` via LibreOffice → `pyxlsb`**
   
   Good targeted replacement if you only need sheet data.

**Tools I Would Not Fully Replace Yet**

1. **LibreOffice for `.doc` / `.ppt`**
   
   Old binary Office formats are messy. LibreOffice is still the best free local converter for these.

2. **ImageMagick + Ghostscript for AI/EPS/PSD visual rendering**
   
   Python can inspect some of these, but rendering visual pages/artboards accurately is much harder. Keep them optional.

3. **Tesseract**
   
   Python OCR libraries exist, but they are large and model-heavy. Replacing `tesseract` may actually make setup worse.

4. **Ghostscript for EPS/AI**
   
   You can wrap it from Python, but you are still depending on Ghostscript underneath.

**Recommended Direction**

I would move to a **Python-first, system-tool fallback** model:

```text
Python library path first
↓
system tool fallback when installed
↓
Markdown limitation note if neither exists
```

Example:

```text
Image metadata:
  Pillow/exifread first
  exiftool fallback

SVG render:
  cairosvg first
  rsvg-convert fallback

Image dimensions/conversion:
  Pillow/pillow-heif first
  sips fallback
  ImageMagick fallback

Audio stream detection:
  PyAV first
  ffprobe fallback

Legacy Office:
  Python libraries where reliable
  LibreOffice fallback

AI/EPS/PSD rendering:
  keep ImageMagick/Ghostscript optional
  use psd-tools for PSD metadata/layers
```

**Senior-Architect Answer**

Yes, replace these first:

```text
exiftool      -> Pillow / exifread
sips          -> Pillow / pillow-heif
rsvg-convert  -> cairosvg
ffprobe       -> PyAV
xlsb path     -> pyxlsb
```

Keep these as optional external tools for now:

```text
LibreOffice
ImageMagick
Ghostscript
Tesseract
```

That gets you fewer system dependencies without making conversion quality worse.