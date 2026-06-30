# Local Markdown Converter

Convert a local mixed-format project into a self-contained Markdown corpus that Claude, Claude Code, Cowork, or another Markdown-oriented reader can search and reason over. The converter handles **PDF, video, Word (.doc/.docx), Excel (.xls/.xlsx/.xlsm/.xlsb), PowerPoint (.ppt/.pptx), RTF, Apple Pages, JSON, images/design files (jpg/png/tif/heic/svg/ai/eps/psd/xd/fig), fonts, plain text, OneNote export notes, and zip archives**.

The conversion runs on your machine only. Claude usage starts later, when you point Claude at the generated Markdown folder and ask questions.

## Architectural contract

- **Local-first:** source files are converted locally; no project content is sent to Claude by the converter.
- **Deterministic orchestration:** Python owns walking, hashing, manifest state, safe archive extraction, atomic writes, reporting, and dispatch.
- **Specialized tools stay specialized:** markitdown, LibreOffice, ImageMagick, Tesseract, ExifTool, fonttools, psd-tools, and mlx-whisper are used where they are stronger than hand-rolled parsing.
- **Capabilities are centralized:** supported extensions, handlers, required tools, optional tools, and format descriptions live in `markdown_converter/capabilities.py`.
- **Failures are structured:** conversion failures carry stable error codes so reports are easier to triage and future automation can act on them.
- **Archives are conservative:** zip files are extracted through a safety policy and are marked complete only after all recursive conversions succeed.

## Quick start

```bash
brew install python@3.13 ffmpeg tesseract
brew install exiftool librsvg imagemagick ghostscript
brew install --cask libreoffice

python3.13 -m venv ~/md-convert-env
source ~/md-convert-env/bin/activate
pip install --upgrade pip
pip install -e '.[apple-silicon-transcription,design]'

convert-to-markdown "/path/to/project" "/path/to/output"
```

Use `convert-to-markdown --force in out` to rebuild everything even when hashes are unchanged.

---

# Part 1 — Install the Converter (macOS)

Do this once. Everything below is free and local. Assumes an Apple-Silicon Mac (M1/M2/M3/M4); Intel notes are called out.

## Step 1 — Homebrew (package manager)

Check whether you already have it: `brew --version`. If not, install it:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

On Apple Silicon the installer prints a "Next steps" block to add Homebrew to your PATH — run it (typically):

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

## Step 2 — System tools

```bash
brew install ffmpeg tesseract
brew install exiftool librsvg        # optional: photo EXIF metadata; render SVGs to PNG
brew install imagemagick ghostscript # optional: render AI/EPS/PSD and odd image formats
brew install --cask libreoffice      # only if you have legacy .doc/.ppt or binary .xlsb files
```

- **ffmpeg** (with `ffprobe`) — reads audio out of videos and detects silent clips.
- **tesseract** — free local OCR for images.
- **exiftool** *(optional)* — adds capture date / camera / GPS to photo `.md` files.
- **librsvg** *(optional)* — renders each SVG to a companion PNG so Claude can see it as a picture.
- **ImageMagick + Ghostscript** *(optional)* — renders all pages/frames/scenes it can expose from TIFF/HEIC edge cases, AI/EPS, and PSD files.
- **LibreOffice** — converts legacy `.doc`/`.ppt` and binary `.xlsb`. Skip it if you have none of those.

## Step 3 — Python environment

Use Python 3.13. (The newest 3.14 can cause `pip` to install an outdated markitdown, because some of its dependencies don't ship 3.14 wheels yet.)

```bash
brew install python@3.13
python3.13 -m venv ~/md-convert-env
source ~/md-convert-env/bin/activate
pip install --upgrade pip
```

## Step 4 — Python packages

```bash
pip install -e '.[apple-silicon-transcription,design]'
```

- **markitdown** — PDF, Word, Excel, PowerPoint, HTML, CSV → Markdown.
- **mlx-whisper** — on-device speech-to-text for audio/video (Apple Silicon). **Intel Mac:** use `pip install openai-whisper` instead, and change the media converter command if you want to use `whisper` instead.
- **fonttools** — reads font metadata.
- **psd-tools** *(optional `design` extra)* — extracts PSD layer names and basic layer geometry when possible.

The Python dependencies live in `pyproject.toml`. For a smaller install without audio transcription or PSD layer inspection, use `pip install -e .`.

For repeatable installs, see `REPRODUCIBILITY.md`. The project uses `pyproject.toml` as the dependency source of truth and documents how to generate a per-machine `requirements-lock.txt` from a clean environment.

## Step 5 — The converter

The project installs a console command named `convert-to-markdown`:

```bash
convert-to-markdown --help
```

If you do not install the project in editable mode, keep `convert_to_markdown.py` and the `markdown_converter/` package folder together and run `python convert_to_markdown.py --help` instead.

## Step 6 — Verify

Run it on a tiny test (see Part 2). The Python converter performs a **preflight check** at startup and will warn you, by name, about any missing required converter tool — so if you forgot to activate the venv, you'll see exactly that rather than a wall of errors.

Preflight is corpus-aware: it scans the input tree first and warns only about required or optional helpers relevant to extensions actually present in that corpus.

## Re-activating in new terminal sessions

A venv applies only to the terminal that activated it. In each new terminal, before running the converter:

```bash
source ~/md-convert-env/bin/activate
```

## What each tool is for

| Tool | Installed via | Used for |
|---|---|---|
| Homebrew | curl script | installing the tools below |
| ffmpeg / ffprobe | `brew install ffmpeg` | audio extraction; silent-video detection |
| tesseract | `brew install tesseract` | OCR of images |
| exiftool *(optional)* | `brew install exiftool` | photo EXIF (date, camera, GPS) |
| librsvg *(optional)* | `brew install librsvg` | render SVG → companion PNG |
| ImageMagick / Ghostscript *(optional)* | `brew install imagemagick ghostscript` | render HEIC/TIFF fallbacks, AI/EPS, PSD pages/frames/scenes |
| LibreOffice | `brew install --cask libreoffice` | legacy `.doc`/`.ppt`, binary `.xlsb` |
| Python 3.13 + venv | `brew install python@3.13` | isolated runtime for the Python tools |
| markitdown | `pip install` | documents → Markdown |
| mlx-whisper | `pip install` | audio/video → transcript |
| fonttools | `pip install` | font metadata |
| psd-tools *(optional)* | `pip install -e '.[design]'` | PSD layer inventory |

## File layout

```text
pyproject.toml              # package metadata, dependencies, extras, console script
REPRODUCIBILITY.md          # repeatable install policy and lock-generation workflow
convert_to_markdown.py      # Python CLI entrypoint
markdown_converter/         # conversion package
  archive.py                # safe zip extraction policy
  capabilities.py           # supported extensions, converter capabilities, tool requirements
  cli.py                    # argument parsing and input validation
  config.py                 # environment-backed runtime settings
  core.py                   # walking, hashing, manifest, report, zip recursion
  converters.py             # registry facade over domain-specific handlers
  errors.py                 # structured conversion error codes
  handlers/                 # document, text, design, visual, and media handlers
  package_extraction.py     # XD/FIG structured JSON/XML/SVG extraction
  manifest.py               # SHA-256 manifest read/write
  report.py                 # final conversion report
  tools.py                  # subprocess/tool discovery helpers
```

## Architecture overview

| Layer | Owns | Notes |
|---|---|---|
| CLI (`cli.py`) | arguments, path validation | Keeps user input validation outside conversion logic. |
| Settings (`config.py`) | force mode and runtime knobs | Environment variables remain fallback configuration. |
| Core (`core.py`) | traversal, hashing, archive recursion, atomic writes | Does not know format internals. |
| Capabilities (`capabilities.py`) | extension support, handler mapping, tool requirements | The first place to edit when adding a format. |
| Handlers (`handlers/`) | actual format conversion | Each handler returns a `ConverterResult`, not ad hoc status strings. |
| Archive policy (`archive.py`) | safe zip validation and extraction | Rejects traversal, symlinks, encrypted entries, and oversized archives. |
| Reports (`report.py`, `errors.py`) | stable failure reporting | Uses structured error codes for triage. |

---

# Part 2 — Run Conversion

## Test with one file first

The quickest sanity check needs no script — convert a single file and eyeball it:

```bash
source ~/md-convert-env/bin/activate
markitdown "/path/to/sample.pdf" -o sample.md
open sample.md
```

For a video sample: `mlx_whisper "/path/to/clip.mp4" -f txt -o . --model mlx-community/whisper-large-v3-turbo --language en` (writes `clip.txt`).

## Run on the whole project

```bash
source ~/md-convert-env/bin/activate
convert-to-markdown "/path/to/project" "/path/to/output"
convert-to-markdown --force "/path/to/project" "/path/to/output"   # reconvert everything
```

Without editable installation, replace `convert-to-markdown` with `python convert_to_markdown.py`.

Runtime settings are explicit CLI flags, with environment variables kept as fallbacks:

```bash
convert-to-markdown \
  --whisper-model mlx-community/whisper-small-mlx \
  --whisper-lang en \
  --render-density 250 \
  "/path/to/project" "/path/to/output"
```

Output mirrors your folder structure, and each file becomes `<full name>.md` (so `hello.pdf` → `hello.pdf.md`, which makes collisions between same-named files of different types impossible). The output folder must be **outside** the input folder (the converter enforces this).

## First run downloads a transcription model

The first time a video is transcribed, mlx-whisper downloads the model (~1.6 GB) and caches it at:

```
~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo/
```

This happens once; later runs reuse it. To store it elsewhere (e.g. an external drive), set this before running (add it to `~/.zshrc` to persist):

```bash
export HF_HOME=/Volumes/MyDrive/hf-cache      # model then caches under $HF_HOME/hub/...
```

The "unauthenticated requests to the HF Hub" message during download is harmless — it just means anonymous, rate-limited downloading.

## What each format becomes

- **Documents** — pdf, docx, pptx, xlsx, xls, html, csv: converted by `markitdown` (preserves headings, lists, tables).
- **doc / ppt (legacy):** LibreOffice → docx/pptx → markitdown.
- **xlsm:** read as a normal xlsx (sheet data kept, macros ignored). **xlsb:** LibreOffice → xlsx first.
- **rtf:** macOS `textutil` → HTML → markitdown.
- **pages:** modern `.pages` is a zip bundle, so the embedded `QuickLook/Preview.pdf` is used (needs "Include preview in document" to have been on when saved — the default).
- **json:** gets a Markdown summary (valid/invalid, top-level type, key/item counts) plus formatted JSON or raw preserved contents.
- **txt:** wrapped in a Markdown document with fenced text content. Existing `.md` / `.markdown` files are copied unchanged.
- **url:** parsed as an Internet Shortcut when possible; the URL becomes a Markdown link, host/scheme and shortcut fields are listed, and raw contents are preserved.
- **jpg / jpeg / png:** the image is copied next to its `.md` and **embedded** (`![name](<name>)`), plus a dimensions line, **EXIF photo metadata** (capture date, camera, GPS — if exiftool is installed), and OCR'd text (tesseract). The embedded image lets Claude *see* it at query time.
- **tif / tiff / heic / heif / hei:** rendered to one PNG per page/frame when the local tools expose multiple images, then embedded in Markdown with metadata and OCR per render.
- **svg:** embedded the same way, plus a **rendered companion PNG** (if librsvg is installed, so Claude sees it as a picture) and extracted text labels.
- **ai / eps:** rendered to one PNG per page/artboard when ImageMagick/Ghostscript can read the file, then OCR'd. Illustrator text saved as outlines may only be searchable through OCR.
- **psd:** renders every composite/layer scene ImageMagick exposes, with metadata and OCR per render. If the `design` Python extra is installed, it also extracts a bounded PSD layer inventory with layer names, visibility, type, and geometry when `psd-tools` can read the file. For full design fidelity, add same-basename PDF/SVG/PNG/HTML exports next to the PSD; the Markdown calls out detected companion exports.
- **xd / fig:** copied next to a generated Markdown note. The converter tries to render every locally visible page/frame, and if the file is a zip-readable package, extracts a structured design summary from JSON-like internals (`.json`, `.agc`, etc.): text strings, named objects/frames/components, colors, asset references, embedded package image assets, package inventory, and bounded raw snippets for traceability. The Markdown also lists best-fidelity export alternatives and detects same-basename PDF/SVG/PNG/JPG/HTML companion exports.
- **one / onetoc2:** OneNote files are proprietary binary notebook containers. The converter writes a Markdown note explaining the limitation; export the notebook or section from OneNote as PDF, DOCX, or HTML for full text conversion.
- **otf / ttf / ttc:** metadata only (family, style, version, glyph count) — fonts hold glyph outlines, not document text.
- **Audio/Video** — mp4, mov, m4v, mkv, avi, webm, mp3, m4a, wav, aac, flac: transcribed on-device with `mlx-whisper`. Silent clips (no audio stream) get a short stub instead of erroring.
- **zip:** safely extracted to a temp dir, then converted recursively into a folder named after the archive (e.g. `archive.zip/`), preserving internal structure and handling nested zips. Extraction rejects path traversal, symlink entries, encrypted entries, and archives that exceed member/expanded-size safety limits; macOS zip metadata is skipped.

A converted image `.md` looks like:

```markdown
# screenshot.png

![screenshot.png](<screenshot.png>)

**Image:** 1272 x 712 px, png

## Text (OCR)
<extracted text…>
```

## Change detection (content hash)

Re-running is cheap and safe. Change detection is by **content hash** — there is no timestamp mode.

- **How it works.** On every run each source file is hashed (SHA-256) and compared with the hash recorded from its last successful conversion. Those hashes are stored in `.convert_hashes` at the root of the output folder. A file is converted only when its output is missing or empty, or its content has actually changed (shown as `-> path`); otherwise it is skipped (`== path (unchanged, skipped)`). Zips are checked at the archive level — skipped if unchanged after a fully successful recursive conversion, wiped and cleanly re-extracted if changed.
- **Why hashing, not timestamps.** Modification times are unreliable: copying, syncing, restoring from backup, or unzipping all reset them, which would otherwise force a needless full reconvert. Hashing ignores mtime entirely and reconverts strictly on real content change, so detection stays correct even after you move or re-sync the whole project.
- **Trade-off.** Every file is read in full to hash it on each run, so large media are re-hashed each run. That is still far cheaper than re-transcribing them, and only changed files are actually reconverted. Hashing is handled inside Python with SHA-256, so no `shasum` or `sha256sum` command is required.
- **Atomic writes.** Each `.md` is built in a temp file and renamed into place only on success, so an interrupted run never leaves a half-written output that a later run mistakes for finished.
- **Deletes partial/failed output.** On any failure (nonzero exit *or* a zero-byte file) the `.md` is removed, so it retries next run while completed files keep skipping. A real failure also surfaces the underlying tool's own message (e.g. markitdown's "include the optional dependency `[xls]`").
- **Archive retry behavior.** An archive hash is recorded only after all inner conversions finish without failures. If a file inside an archive fails, the archive is retried on the next run even when the zip bytes are unchanged.
- **Force a full rebuild:** `convert-to-markdown --force in out` reconverts everything and rewrites the manifest. `FORCE=1` is still accepted for existing scripts, but `--force` is preferred for normal use.

## Detailed end-of-run report

Each run ends with counts and the full lists of skipped and failed files, with reasons:

```
================= Conversion report =================
When:    Tue Jun 30 14:05:12 2026
Source:  /path/to/project
Output:  /path/to/output
Mode:    content-hash

Converted: 4
Skipped:   1
Failed:    2

Skipped files (1):
  == Docs/weird.xyz (unsupported .xyz)

Failed files (2):
  !! Docs/bundle.zip/inner/bad.ppt (needs LibreOffice: brew install --cask libreoffice [missing_tool])
  !! Docs/bundle.zip (archive contains failed conversions [archive_child_failure])
```

Skipped reasons: unchanged / unsupported / archive unchanged. Failed reasons include structured error codes such as `missing_tool`, `external_command_failed`, `empty_output`, `unsafe_archive`, `archive_extraction_failed`, `archive_child_failure`, `embedded_preview_missing`, and `transcription_failed`. Files inside an archive are shown with their full path so you can find them. The same information is saved as typed JSON in `_conversion_report.json`, so the full lists survive even when they scroll past in the terminal and can be consumed by automation.

## Safety checks

The converter fails fast or warns on common mistakes: it errors if the input folder is missing or if the **output folder is inside the input** (which would otherwise re-ingest its own `.md` output); it prints a **preflight heads-up** listing missing required tools and optional helpers for the extensions found in the current corpus; LibreOffice conversions use an **isolated profile**, so `.doc`/`.ppt`/`.xlsb` still convert even when you have the LibreOffice app open; **hidden/dot directories** (`.git`, `.vscode`, `.DS_Store`, macOS zip cruft, etc.) are pruned rather than converted; zip extraction rejects unsafe paths; and each `.md` is written to a temp file and **atomically renamed** into place, so an interrupted run never leaves a half-written output that later gets mistaken for "done."

A few edge cases are knowingly left as-is: interrupting a *transcription* with Ctrl-C may leave a stray `.txt` in the output (harmless, not re-ingested); old bundle-style `.pages` (a folder rather than a single file) isn't handled; symlinked files are not followed; and **deleted or renamed source files leave their old `.md` orphaned** in the output (the tool only adds and updates — it never deletes outputs for sources that vanished). If your corpus churns and you want orphans cleaned, that can be added as an opt-in clean pass.

## Caveats

- **Transcription speed scales with your chip.** A base M1 runs roughly real-time (a 10-minute clip ≈ 10 minutes); newer chips are several times faster. On an 8 GB Air, use `--whisper-model mlx-community/whisper-small-mlx` if you hit memory pressure.
- **Non-speech audio** (e.g. race footage with only engine noise) won't crash but yields little or garbled text — glance at those transcripts.
- **PowerPoint speaker notes are dropped** by markitdown — extract separately if your decks depend on them.
- **Scanned / image-only PDFs** come out nearly empty (markitdown's only OCR path is a paid LLM). Free local fix: `brew install ocrmypdf`, then `ocrmypdf in.pdf out.pdf` before converting.
- **OCR quality** (images): tesseract reads crisp UI text well but struggles with low-resolution images, stylized fonts, or text over busy backgrounds. For image-heavy questions, rely on query-time visual reasoning rather than the OCR text.
- **SVG:** Claude reads an SVG as XML (markup + labels), not as a rendered picture. If a diagram's *visual* layout matters, render a companion PNG (`brew install librsvg`) so Claude can view it.
- **Fonts, icon-only SVGs, text-free images** behave as *index entries* — they tell Claude a file exists and what it's called, but contribute little to synthesized answers.
- **Output size grows** because images are duplicated into the output folder — the trade for a self-contained, portable result.

---

# Part 3 — Query the Markdown with Claude

Point Claude at the output folder. This is the only stage that uses your subscription.

## With Claude Code or Cowork (best for local files)

Both are included with Pro/Max — one subscription covers Claude on web/desktop/mobile *plus* Claude Code. In a terminal:

```bash
cd "/path/to/output"
claude
```

…or open the folder in the Claude desktop app (Cowork is the non-developer-framed version, same engine). Then ask in plain language; it searches the tree and reads only the files relevant to each question, including the embedded images for visual questions.

Starter prompts:

- "Give me a structured overview of this project and how it's organized."
- "Where is `<module X>` described? Summarize how it behaves, and cite the files."
- "Compare how `<topic>` is handled across these documents, and flag any contradictions."
- "List every document that mentions `<thing>`, with a one-line note on each."

## With claude.ai Projects (browser / mobile)

Upload the Markdown (and the copied image files) into a Project's knowledge base; it retrieves relevant pieces per question automatically. Limits: 30 MB per file; the knowledge base holds many files.

## Get better, verifiable answers

- Ask Claude to **answer only from the project files**, to **cite the file/section** behind each claim, and to **say explicitly when something isn't documented**. This curbs guessing and lets you verify.
- For a module question, ask it to **find all relevant material first, then synthesize**. Claude Code searches iteratively (read, realize it needs more, search again), so it gathers context scattered across documents.

## What it can and can't answer

- **Synthesis across files — yes.** It combines a requirement from a spec PDF, a clarification from a meeting transcript, and a figure from a spreadsheet into one coherent answer; comparisons and cross-document summaries are in scope.
- **Documented module behavior — yes.** Reasoning is only as reliable as the description it draws from.
- **How the *code* actually behaves — point Claude Code at the source code directly,** not a Markdown copy of it.
- **Visual questions** ("what does this mockup/chart show") — yes, at query time: the image travels with its `.md`, so Claude opens and reasons about it.
- **The limit:** behavior written down nowhere — only in code you didn't include, or in someone's head — can't be recovered. You'll correctly get "not specified in the provided material," not a confident guess.

---

# Part 4 — Architecture and Design Rationale

## Converter capability model

Adding a format should be a small, predictable change:

1. Add or update a `ConverterCapability` in `markdown_converter/capabilities.py`.
2. Point that capability at a handler method implemented under `markdown_converter/handlers/`.
3. Return `ConverterResult.failed(...)` with a `ConversionErrorCode` for failures.
4. Add or adjust README format behavior and a focused fixture.

This keeps format support discoverable and prevents extension lists, preflight warnings, and dispatch logic from drifting apart.

## Operational guarantees

- Completed files are skipped by content hash, not timestamp.
- Outputs are written through `.partial` files and atomically renamed into place.
- Failed or empty outputs are removed so the next run retries them.
- Archive hashes are recorded only after all inner conversions succeed.
- The converter never deletes orphaned outputs for removed source files unless a future explicit clean mode is added.

## You don't need RAG or skills for this

For a single project you query yourself, an agentic tool that reads your filesystem directly is simpler and usually better than building retrieval infrastructure.

- **Agentic search beats indexing here.** Claude Code searches the folder and reads files on command rather than pre-indexing — an approach Anthropic finds more flexible and effective than full codebase indexing.
- **Skills are not knowledge storage.** A skill tells Claude *how to do a recurring task*, not *what's in your files*. Optional, not needed for Q&A.
- **`CLAUDE.md` and memory are optional.** A `CLAUDE.md` at the project root is a notes file Claude Code reads automatically — useful for persistent context, but not required to start.

## What drives cost and speed

It's how many tokens enter the model's context window *per query* — not the file format on disk. Levers, in order of impact: **retrieval** (only the relevant slice per query — biggest lever), **caching** (reuse a static context cheaply — API only), **format** (clean Markdown vs re-extracted binary — modest), **model choice** (lighter model for simple lookups).

## Subscription vs. API

| Mechanism | On a Claude.ai subscription? |
|---|---|
| Claude Code / Cowork agentic search over local files | Yes — included with Pro & Max |
| claude.ai Projects (managed retrieval over a knowledge base) | Yes |
| Custom RAG (embeddings + vector database) | No — API only |
| Prompt-caching control (`cache_control` breakpoints) | No — API only |

On a subscription, your retrieval comes from Claude Code/Cowork or Projects — not a DIY RAG pipeline. (For reference, on the API a prompt-cache read costs ~10% of the standard input price.) On Pro/Max, usage limits are **shared across Claude and Claude Code**, so "least tokens/credits" really means "don't burn your usage allowance" — which is why retrieval (small per-query context) matters more than stuffing everything in.

## Approach comparison

| Approach | Setup | Tokens / query | Upfront cost | Latency | Accuracy | Scales large | On subscription |
|---|---|---|---|---|---|---|---|
| **Agentic search over a Markdown folder** (Claude Code / Cowork) | Low | Medium — search + files opened | ~none | Medium | High on located/keyword facts; weaker on cross-doc synthesis | Moderate | Yes |
| **RAG** (embeddings + vector store) | High | Lowest — top-k chunks only | Embed once (cents) | Lowest | Strong semantic recall; can miss on synthesis / poor chunking | Best | No (API) |
| **Whole corpus in context + prompt caching** | Low | Highest raw, ~0.1× on cache hits | ~none | Higher | Highest — model sees everything | Limited to context window | No (API) |
| **claude.ai Projects** (managed retrieval) | Lowest | Flat on subscription; retrieval keeps it small | none | Low–Medium | Good; little tuning control | Good (within limits) | Yes |

Lowest tokens (RAG) and highest accuracy (full context) pull in opposite directions; on a subscription, Claude Code/Cowork or Projects give you the retrieval benefit without building any of it.

---

# Part 5 — Operations and Maintenance

These started as optional add-ons and are now built in:

- **EXIF / photo metadata** — automatic when `exiftool` is installed (`brew install exiftool`); adds capture date, camera, and GPS to photo `.md` files.
- **SVG rasterization** — automatic when `librsvg` is installed (`brew install librsvg`); renders a companion PNG per SVG so Claude sees diagrams as pictures, not just XML.
- **Content-hash change detection** — always on. Each run hashes every source (SHA-256), stores the hashes in `.convert_hashes`, and reconverts only changed or missing files. See *Change detection* above for the trade-off.
- **Report file** — always written to `_conversion_report.json` in the output folder, in addition to the terminal summary.

## Developer checks

Run these before committing converter changes:

```bash
python3 -m compileall -q markdown_converter convert_to_markdown.py
git --no-pager diff --check -- README.md REPRODUCIBILITY.md pyproject.toml markdown_converter
```

For behavior changes, add a temporary fixture that exercises the touched path: unchanged skip, `--force`, unsafe zip rejection, archive retry, package extraction, or the specific format handler being edited.

## Future useful additions

- `--clean-orphans` to delete outputs whose source file was removed or renamed.
- A pytest suite around registry dispatch, archive safety, manifest behavior, and built-in text/json/url conversions.
- Optional OCR language settings for non-English image text (`brew install tesseract-lang`).

---

## Sources / further reading

- Claude Code FAQ (search vs. indexing): https://support.claude.com/en/articles/12386420-claude-code-faq
- How Claude Code works: https://code.claude.com/docs/en/how-claude-code-works
- Use Claude Code with Pro/Max: https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan
- Upload files / Projects: https://support.claude.com/en/articles/8241126-upload-files-to-claude
- Prompt caching (API): https://docs.claude.com/en/docs/build-with-claude/prompt-caching
- Embeddings (API): https://docs.claude.com/en/docs/build-with-claude/embeddings
- markitdown: https://pypi.org/project/markitdown/
- mlx-whisper: https://pypi.org/project/mlx-whisper/
