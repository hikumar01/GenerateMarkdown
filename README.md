# Querying a Local, Mixed-Format Project with Claude — Practical Guide

## The situation this covers

A local project folder (with nested subfolders) holding mixed files — **PDF, video, Word (.doc/.docx), Excel (.xlsx), PowerPoint (.ppt/.pptx), and plain text**. It is not in git and has no skills, memory, or `CLAUDE.md`. The files rarely change. The goal: ask many specific questions against them, on a **Claude.ai Pro/Max subscription**, while minimizing usage, maximizing speed, and keeping answers accurate.

---

## Core principles

**You do not need to build RAG or define skills for this.** For a single project you query yourself, the simplest and usually best method is an agentic tool that reads your filesystem directly and opens the relevant files on demand.

- **Agentic search beats indexing here.** Tools like Claude Code search the folder and read files on command rather than pre-indexing everything — an approach Anthropic finds more flexible and effective than full codebase indexing.
- **Skills are not knowledge storage.** A skill is a reusable instruction set telling Claude *how to perform a recurring task*, not a place to store *what is in your files*. Optional, and not needed for Q&A.
- **`CLAUDE.md` and memory are optional.** A `CLAUDE.md` at the project root is a notes file Claude Code reads automatically — handy for persistent context, but not required to start asking questions.

**What actually drives cost and speed** is how many tokens enter the model's context window *per query* — not the file format on disk. The levers, in order of impact:

1. **Retrieval** — get only the relevant slice into context per query. *(Biggest lever.)*
2. **Caching** — reuse the same context cheaply across queries. *(API only — see below.)*
3. **Format** — clean text/Markdown vs. re-extracted binary. *(One-time, modest.)*
4. **Model choice** — a lighter model for simple lookups.

---

## What is available on a subscription vs. the API

| Mechanism | On a Claude.ai subscription? |
|---|---|
| Claude Code / Cowork agentic search over local files | Yes — included with Pro & Max |
| claude.ai Projects (managed retrieval over a knowledge base) | Yes |
| Custom RAG (embeddings + vector database) | No — API only |
| Prompt-caching control (`cache_control` breakpoints) | No — API only |

So on a subscription your "retrieval" comes from **Claude Code / Cowork** (searches your local folder) or **Projects** (retrieves over uploaded docs) — not a DIY RAG pipeline. (For reference, on the API, prompt-cache reads cost ~10% of the standard input price, which is why caching helps API workloads that reuse a large static context.)

---

## Ways to query the project

- **Claude Code or Cowork (recommended for local files).** Included with Pro/Max — one subscription covers Claude on web/desktop/mobile *plus* Claude Code. Point it at the project folder; it searches and reads only the files relevant to each question. Handles nested folders, no upload, always reflects the current files. Cowork is the non-developer-framed version (same engine underneath).
- **claude.ai Projects.** Upload your files into a Project's knowledge base; it retrieves relevant pieces per query automatically (managed RAG). Best if you want browser/mobile access. Limits: 30 MB per file; the knowledge base holds many files (well beyond a single chat's cap).
- **Plain chat upload.** Fine for a handful of files, but it flattens folder structure and caps at ~30 MB/file and 20 files per conversation — not ideal for a large, multi-level project.

> **Usage note:** On Pro/Max, limits are **shared across Claude and Claude Code**. "Least tokens/credits" really means "don't burn your usage allowance" — which is exactly why retrieval (a small per-query context) matters more than stuffing everything into each message.

---

## Approach comparison (the general landscape)

| Approach | Setup | Tokens / query | Upfront cost | Latency | Accuracy | Scales to large corpus | On subscription |
|---|---|---|---|---|---|---|---|
| **Agentic search over a Markdown folder** (Claude Code / Cowork) | Low | Medium — search + files opened | ~none | Medium | High on located/keyword facts; weaker on cross-document synthesis | Moderate | Yes |
| **RAG** (embeddings + vector store) | High | Lowest — top-k chunks only | Embed once (cents) | Lowest | Strong semantic recall; can miss on synthesis / poor chunking | Best | No (API) |
| **Whole corpus in context + prompt caching** | Low | Highest raw, ~0.1× on cache hits | ~none | Higher | Highest — model sees everything | Limited to context window | No (API) |
| **claude.ai Projects** (managed retrieval) | Lowest | Flat on subscription; retrieval keeps it small | none | Low–Medium | Good; little tuning control | Good (within limits) | Yes |

**The core tension:** lowest tokens (RAG) and highest accuracy (full context) pull in opposite directions. Hybrids — retrieve to narrow down, with generous chunks and a reranker — are what most production setups land on. On a subscription, Claude Code/Cowork or Projects give you the retrieval benefit without building any of that.

---

## Preprocess once: convert to Markdown + transcribe video

Because the corpus is static, a one-time conversion pays off on every future query.

- **Videos are otherwise invisible.** Claude cannot read a video file; without a transcript, that content contributes nothing to any answer. Transcribing once turns speech into searchable text — and since transcription is the slow step, doing it once (not per query) is the point.
- **Avoids re-parsing binaries each query.** Otherwise every query re-extracts text from PDFs/Office files, which is slower and drags in layout noise (headers, footers, broken tables) that bloats context and confuses retrieval. Clean Markdown preserves structure (headings, lists, tables) and reads leaner.
- **Uniform, searchable, chunkable text.** Both Claude Code's grep-and-read and Projects' retrieval work best over plain text. One Markdown layer = one consistent way to find content across every format.

In short: this is less about slashing per-query tokens and more about making the video content *exist* for querying, eliminating repeated conversion, and giving retrieval clean input.

---

## Convert everything locally and free (macOS, Apple Silicon)

All conversion runs on your Mac with open-source tools — **zero Claude usage**. (Your subscription is only used later, when you query the Markdown.)

**Tools**

- `markitdown` (Microsoft) → PDF, DOCX, PPTX, XLSX/XLS, HTML, CSV → Markdown (preserves headings, lists, tables, links).
- `mlx-whisper` + `ffmpeg` → video/audio → on-device transcript (Apple-Silicon optimized, no API key, nothing leaves your machine).
- Plain text → copied as-is.
- `libreoffice` (optional) → only needed for legacy `.doc` / `.ppt`.

**One-time setup (Terminal)**

```bash
brew install ffmpeg
brew install --cask libreoffice            # only if you have legacy .doc/.ppt
python3 -m venv ~/md-convert-env && source ~/md-convert-env/bin/activate
pip install 'markitdown[pdf,docx,pptx,xlsx]' mlx-whisper


pip install 'markitdown[pdf,docx,pptx,xlsx,xls]' mlx-whisper
```

**Run the conversion** — use the provided script `convert_to_markdown.sh`:

```bash
source ~/md-convert-env/bin/activate
chmod +x convert_to_markdown.sh
./convert_to_markdown.sh "/path/to/project" "/path/to/output"
```

It mirrors your folder structure into the output folder, so each `.md` lands in the same layout as the original.

**Caveats**

- **Transcription speed scales with your chip.** A base M1 runs roughly real-time (a 10-minute clip ≈ 10 minutes); newer chips are several times faster. On an 8 GB Air, set the model to `mlx-community/whisper-small-mlx` (top of the script) if you hit memory pressure. The model auto-downloads on first run and caches in `~/.cache/huggingface`.
- **PowerPoint speaker notes are dropped** by markitdown — extract them separately (e.g. `python-pptx`) if your decks depend on them.
- **Scanned / image-only PDFs** come out nearly empty (markitdown's only OCR path is a paid LLM). Free local fix: `brew install ocrmypdf`, then `ocrmypdf in.pdf out.pdf` before converting.
- **Intel MacBook Air:** mlx-whisper is Apple-Silicon-only — use `pip install openai-whisper` and replace `mlx_whisper` with `whisper` in the script (nearly identical flags).
- **Same-named files of different types** in one folder (e.g. `report.pdf` + `report.docx`) both map to `report.md` — rename one beforehand if that applies.

---

## Recommended end-to-end workflow

1. Run `convert_to_markdown.sh` on the project → a clean Markdown tree. *(No Claude usage.)*
2. Point **Claude Code or Cowork** at that Markdown folder (no upload needed), or load it into a **Project**.
3. Ask your questions. Retrieval keeps each query small → faster answers, less of your usage allowance spent.

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
