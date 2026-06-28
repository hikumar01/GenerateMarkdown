# Querying a Local, Mixed-Format Project with Claude — Complete Guide

A project folder of mixed files — **PDF, video, Word (.doc/.docx), Excel (.xls/.xlsx/.xlsm/.xlsb), PowerPoint (.ppt/.pptx), RTF, Apple Pages, JSON, images (jpg/png/svg), fonts, plain text, and zip archives** — not in git, with no skills, memory, or `CLAUDE.md`, that rarely changes. This turns it into something you can ask specific questions about with Claude on a **Pro/Max subscription**, while keeping cost and latency low.

**Two stages:** (1) convert everything to Markdown once, locally and free; (2) point Claude at the Markdown and ask. The conversion runs on your machine only — **no Claude usage**. Your subscription is spent only at query time.

---

# Part 1 — One-time setup (macOS)

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
brew install --cask libreoffice      # only if you have legacy .doc/.ppt or binary .xlsb files
```

- **ffmpeg** (with `ffprobe`) — reads audio out of videos and detects silent clips.
- **tesseract** — free local OCR for images.
- **exiftool** *(optional)* — adds capture date / camera / GPS to photo `.md` files.
- **librsvg** *(optional)* — renders each SVG to a companion PNG so Claude can see it as a picture.
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
pip install 'markitdown[pdf,docx,pptx,xlsx,xls]' mlx-whisper fonttools
```

- **markitdown** — PDF, Word, Excel, PowerPoint, HTML, CSV → Markdown.
- **mlx-whisper** — on-device speech-to-text for audio/video (Apple Silicon). **Intel Mac:** use `pip install openai-whisper` instead, and change `mlx_whisper` to `whisper` in the script (near-identical flags).
- **fonttools** — reads font metadata.

## Step 5 — The script

Save `convert_to_markdown.sh` somewhere convenient and make it executable:

```bash
chmod +x convert_to_markdown.sh
```

## Step 6 — Verify

Run it on a tiny test (see Part 2). The script also performs a **preflight check** at startup and will warn you, by name, about any tool it can't find — so if you forgot to activate the venv, you'll see exactly that rather than a wall of errors.

## Re-activating in new terminal sessions

A venv applies only to the terminal that activated it. In each new terminal, before running the script:

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
| LibreOffice | `brew install --cask libreoffice` | legacy `.doc`/`.ppt`, binary `.xlsb` |
| Python 3.13 + venv | `brew install python@3.13` | isolated runtime for the Python tools |
| markitdown | `pip install` | documents → Markdown |
| mlx-whisper | `pip install` | audio/video → transcript |
| fonttools | `pip install` | font metadata |

---

# Part 2 — Convert the project

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
./convert_to_markdown.sh "/path/to/project" "/path/to/output"
FORCE=1 ./convert_to_markdown.sh "/path/to/project" "/path/to/output"   # reconvert everything
```

Output mirrors your folder structure, and each file becomes `<full name>.md` (so `hello.pdf` → `hello.pdf.md`, which makes collisions between same-named files of different types impossible). The output folder must be **outside** the input folder (the script enforces this).

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
- **json:** pretty-printed inside a fenced block (still fully searchable).
- **url:** the shortcut's `URL=` line becomes a Markdown link.
- **jpg / jpeg / png:** the image is copied next to its `.md` and **embedded** (`![name](<name>)`), plus a dimensions line, **EXIF photo metadata** (capture date, camera, GPS — if exiftool is installed), and OCR'd text (tesseract). The embedded image lets Claude *see* it at query time.
- **svg:** embedded the same way, plus a **rendered companion PNG** (if librsvg is installed, so Claude sees it as a picture) and extracted text labels.
- **otf / ttf / ttc:** metadata only (family, style, version, glyph count) — fonts hold glyph outlines, not document text.
- **Audio/Video** — mp4, mov, m4v, mkv, avi, webm, mp3, m4a, wav, aac, flac: transcribed on-device with `mlx-whisper`. Silent clips (no audio stream) get a short stub instead of erroring.
- **zip:** extracted to a temp dir, then converted recursively into a folder named after the archive (e.g. `archive.zip/`), preserving internal structure and handling nested zips.

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

- **How it works.** On every run each source file is hashed (SHA-256) and compared with the hash recorded from its last successful conversion. Those hashes are stored in `.convert_hashes` at the root of the output folder. A file is converted only when its output is missing or empty, or its content has actually changed (shown as `-> path`); otherwise it is skipped (`== path (unchanged, skipped)`). Zips are checked at the archive level — skipped if unchanged, wiped and cleanly re-extracted if changed.
- **Why hashing, not timestamps.** Modification times are unreliable: copying, syncing, restoring from backup, or unzipping all reset them, which would otherwise force a needless full reconvert. Hashing ignores mtime entirely and reconverts strictly on real content change, so detection stays correct even after you move or re-sync the whole project.
- **Trade-off.** Every file is read in full to hash it on each run, so large media are re-hashed each run. That is still far cheaper than re-transcribing them, and only changed files are actually reconverted. (`shasum` ships with macOS and is required; if neither `shasum` nor `sha256sum` is found, the script warns and falls back to reconverting everything each run.)
- **Atomic writes.** Each `.md` is built in a temp file and renamed into place only on success, so an interrupted run never leaves a half-written output that a later run mistakes for finished.
- **Deletes partial/failed output.** On any failure (nonzero exit *or* a zero-byte file) the `.md` is removed, so it retries next run while completed files keep skipping. A real failure also surfaces the underlying tool's own message (e.g. markitdown's "include the optional dependency `[xls]`").
- **Force a full rebuild:** `FORCE=1 ./convert_to_markdown.sh in out` reconverts everything and rewrites the manifest.

## Detailed end-of-run report

Each run ends with counts and the full lists of skipped and failed files, with reasons:

```
================= Summary =================
Converted: 4
Skipped:   1
Failed:    2

Skipped files (1):
  == Docs/weird.xyz (unsupported .xyz)

Failed files (2):
  !! Docs/bundle.zip/inner/bad.ppt (needs LibreOffice (brew install --cask libreoffice))
  !! Docs/broken.doc (needs LibreOffice (brew install --cask libreoffice))

Output: /path/to/output
```

Skipped reasons: unchanged / unsupported / archive unchanged. Failed reasons: needs LibreOffice, no embedded preview, empty output, transcription failed, unzip failed. Files inside an archive are shown with their full path so you can find them. The same report is also saved to `_conversion_report.txt` in the output folder, so the full lists survive even when they scroll past in the terminal.

## Safety checks

The script fails fast or warns on common mistakes: it errors if the input folder is missing or if the **output folder is inside the input** (which would otherwise re-ingest its own `.md` output); it prints a **preflight heads-up** listing any missing tools; LibreOffice conversions use an **isolated profile**, so `.doc`/`.ppt`/`.xlsb` still convert even when you have the LibreOffice app open; **hidden/dot directories** (`.git`, `.vscode`, `.DS_Store`, macOS zip cruft, etc.) are pruned rather than converted; and each `.md` is written to a temp file and **atomically renamed** into place, so an interrupted run never leaves a half-written output that later gets mistaken for "done."

A few edge cases are knowingly left as-is: a *failure inside an unchanged archive* isn't retried unless the archive changes or you pass `FORCE=1`; interrupting a *transcription* with Ctrl-C may leave a stray `.txt` in the output (harmless, not re-ingested); old bundle-style `.pages` (a folder rather than a single file) isn't handled; symlinked files are not followed; and **deleted or renamed source files leave their old `.md` orphaned** in the output (the tool only adds and updates — it never deletes outputs for sources that vanished). If your corpus churns and you want orphans cleaned, that can be added as an opt-in `CLEAN=1` pass.

## Caveats

- **Transcription speed scales with your chip.** A base M1 runs roughly real-time (a 10-minute clip ≈ 10 minutes); newer chips are several times faster. On an 8 GB Air, set the model to `mlx-community/whisper-small-mlx` (top of the script) if you hit memory pressure.
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

# Part 4 — Why this design (background)

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

# Part 5 — Tuning & toggles

These started as optional add-ons and are now built in:

- **EXIF / photo metadata** — automatic when `exiftool` is installed (`brew install exiftool`); adds capture date, camera, and GPS to photo `.md` files.
- **SVG rasterization** — automatic when `librsvg` is installed (`brew install librsvg`); renders a companion PNG per SVG so Claude sees diagrams as pictures, not just XML.
- **Content-hash change detection** — always on. Each run hashes every source (SHA-256), stores the hashes in `.convert_hashes`, and reconverts only changed or missing files. See *Change detection* above for the trade-off.
- **Report file** — always written to `_conversion_report.txt` in the output folder, in addition to the terminal.

Still genuinely optional (ask if you want them): OCR language packs for non-English images (`brew install tesseract-lang`, then set a language in the script), or a `CLEAN=1` pass that deletes outputs whose source was removed or renamed.

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
