#!/usr/bin/env bash
# convert_to_markdown.sh  (v4.1 - content-hash incremental, hardened)
# =============================================================================
# Batch-convert a mixed-format project folder to Markdown, locally and FREE.
# Mirrors the input folder structure into the output folder.
# Output naming:  <full original name>.md     e.g.  hello.pdf -> hello.pdf.md
# (so two files that differ only by extension never collide).
#
# CHANGE DETECTION  --  content hash (the only mode)
#   On every run, each source file is hashed (SHA-256) and compared with the
#   hash recorded from its last successful conversion. Those hashes live in
#   ".convert_hashes" at the root of the output folder. A file is (re)converted
#   only when its output is missing/empty OR its content has changed.
#
#   Why hashing instead of timestamps: file modification times are unreliable
#   -- copying, syncing, restoring from backup, or unzipping all reset them,
#   which would force a needless full reconvert. Content hashing ignores mtime
#   entirely and reconverts strictly on real content change.
#
#   Trade-off: every file is read in full to hash it each run, so large media
#   are re-hashed each run. That is still far cheaper than re-transcribing them,
#   and only changed files are actually reconverted.
#
#   FORCE=1   reconvert everything regardless of hashes, and rewrite the manifest.
#
# RELIABILITY
#   * Atomic writes: each .md is built in a temp file and renamed into place only
#     on success, so an interrupted run never leaves a half-written output.
#   * Failed or empty outputs are deleted, so they are retried on the next run.
#   * Hidden/dot directories (.git, .vscode, .DS_Store, macOS zip cruft) are skipped.
#   * A detailed report is printed AND saved to "_conversion_report.txt".
#
# SUPPORTED FORMATS
#   pdf docx doc pptx ppt xlsx xls xlsm xlsb rtf pages html csv json url txt md
#   jpg jpeg png tif tiff heic heif hei  (image embedded/rendered + EXIF metadata + OCR)
#   svg           (embedded + rendered PNG companion + extracted text labels)
#   ai eps psd    (rendered pages/frames/scenes + metadata + OCR)
#   xd fig        (rendered pages/frames + package assets/inventory when locally readable)
#   one onetoc2   (conversion note; export from OneNote to PDF/DOCX/HTML for full text)
#   otf ttf ttc   (font metadata only)
#   mp4 mov m4v mkv avi webm mp3 m4a wav aac flac  (transcribed on-device)
#   zip           (extracted into a same-named folder, converted recursively)
#
# Runs 100% on your Mac -- no Claude or any other API usage.
# =============================================================================
# ONE-TIME SETUP (Terminal):
#   brew install ffmpeg tesseract
#   brew install exiftool librsvg imagemagick ghostscript
#                                           # OPTIONAL: EXIF metadata; SVG/vector/PSD rendering
#   brew install --cask libreoffice        # needed for: doc, ppt, xlsb
#   python3.13 -m venv ~/md-convert-env && source ~/md-convert-env/bin/activate
#   pip install --upgrade pip
#   pip install 'markitdown[pdf,docx,pptx,xlsx,xls]' mlx-whisper fonttools
#   # shasum ships with macOS and is required for change detection.
#
# RUN:
#   source ~/md-convert-env/bin/activate
#   chmod +x convert_to_markdown.sh
#   ./convert_to_markdown.sh "/path/to/project" "/path/to/output"
#   FORCE=1 ./convert_to_markdown.sh "/path/to/project" "/path/to/output"   # reconvert all
# =============================================================================

set -uo pipefail

SRC="${1:?Usage: ./convert_to_markdown.sh <input_folder> <output_folder>}"
OUT="${2:?Usage: ./convert_to_markdown.sh <input_folder> <output_folder>}"
SRC="${SRC%/}"; OUT="${OUT%/}"
FORCE="${FORCE:-0}"

# --- Settings ----------------------------------------------------------------
WHISPER_MODEL="mlx-community/whisper-large-v3-turbo"   # smaller/faster: mlx-community/whisper-small-mlx
WHISPER_LANG="en"                                      # "" = auto-detect
RENDER_DENSITY="${RENDER_DENSITY:-200}"                # DPI for vector/PDF-like formats rendered by ImageMagick
# -----------------------------------------------------------------------------

# --- Validate inputs ---------------------------------------------------------
[ -d "$SRC" ] || { echo "ERROR: input folder not found: $SRC" >&2; exit 1; }
mkdir -p "$OUT" || { echo "ERROR: cannot create output folder: $OUT" >&2; exit 1; }
SRC_ABS="$(cd "$SRC" && pwd)"; OUT_ABS="$(cd "$OUT" && pwd)"
case "$OUT_ABS/" in
  "$SRC_ABS"/*) echo "ERROR: output ($OUT) is inside input ($SRC). Choose a separate output folder." >&2; exit 1 ;;
esac

SOFFICE="$(command -v soffice || echo /Applications/LibreOffice.app/Contents/MacOS/soffice)"

# --- Content hashing (macOS: shasum; Linux: sha256sum) -----------------------
hash_of() {
  if   command -v shasum    >/dev/null 2>&1; then shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then sha256sum    "$1" 2>/dev/null | awk '{print $1}'
  else echo ""; fi
}

# --- Preflight: warn (non-fatal) about missing tools -------------------------
warn_missing=""
for t in markitdown python3 mlx_whisper ffprobe tesseract; do
  command -v "$t" >/dev/null 2>&1 || warn_missing="$warn_missing $t"
done
[ -x "$SOFFICE" ] || warn_missing="$warn_missing soffice(LibreOffice)"
if [ -n "$warn_missing" ]; then
  echo "(heads up) tools not found:$warn_missing" >&2
  echo "           related files will be skipped or fail. If unexpected, activate your venv:" >&2
  echo "           source ~/md-convert-env/bin/activate" >&2
  echo >&2
fi
if [ -z "$(hash_of /dev/null)" ]; then
  echo "(WARNING) no 'shasum' or 'sha256sum' found -> change detection is disabled;" >&2
  echo "          every file will be reconverted on every run." >&2
  echo >&2
fi

# --- Run tallies + hash manifest (files, to survive the find|while subshell) ---
STATS_DIR="$(mktemp -d)"
: > "$STATS_DIR/converted"; : > "$STATS_DIR/skipped"; : > "$STATS_DIR/failed"
NEW_MANIFEST="$STATS_DIR/newhashes"; : > "$NEW_MANIFEST"   # built this run; replaces the old one at the end
OLD_MANIFEST="$OUT/.convert_hashes"                        # hashes from the previous run
trap 'rm -rf "$STATS_DIR"' EXIT
record()      { printf '%s\n' "$2" >> "$STATS_DIR/$1"; }
count()       { local n; n="$(wc -l < "$STATS_DIR/$1" 2>/dev/null)"; echo "${n//[[:space:]]/}"; }
old_hash()    { awk -F'\t' -v k="$1" '$1==k{print $2; exit}' "$OLD_MANIFEST" 2>/dev/null; }   # disp -> stored hash
record_hash() { printf '%s\t%s\n' "$1" "$2" >> "$NEW_MANIFEST"; }                             # remember disp -> hash

rendered_count() {
  find "$1" -maxdepth 1 -type f -name 'page-*.png' -size +0c 2>/dev/null | wc -l | tr -d '[:space:]'
}

render_pages() {
  local f="$1" asset_dir="$2"
  rm -rf "$asset_dir"; mkdir -p "$asset_dir"
  if command -v magick >/dev/null 2>&1; then
    magick -density "$RENDER_DENSITY" "$f" -auto-orient "$asset_dir/page-%03d.png" >/dev/null 2>&1
    [ "$(rendered_count "$asset_dir")" -gt 0 ] && return 0
  fi
  rm -f "$asset_dir"/page-*.png
  if command -v convert >/dev/null 2>&1; then
    convert -density "$RENDER_DENSITY" "$f" -auto-orient "$asset_dir/page-%03d.png" >/dev/null 2>&1
    [ "$(rendered_count "$asset_dir")" -gt 0 ] && return 0
  fi
  rm -f "$asset_dir"/page-*.png
  if command -v sips >/dev/null 2>&1 && sips -s format png "$f" --out "$asset_dir/page-000.png" >/dev/null 2>&1 && [ -s "$asset_dir/page-000.png" ]; then
    return 0
  fi
  rm -rf "$asset_dir"
  return 1
}

print_image_details() {
  local image="$1"
  if command -v sips >/dev/null 2>&1; then
    sips -g pixelWidth -g pixelHeight -g format "$image" 2>/dev/null \
      | awk '/pixelWidth/{w=$2}/pixelHeight/{h=$2}/format:/{fmt=$2}END{if(w)printf "**Image:** %s x %s px, %s\n\n", w, h, fmt}'
  elif command -v identify >/dev/null 2>&1; then
    identify -format '**Image:** %w x %h px, %m\n\n' "$image" 2>/dev/null
  fi
}

print_file_metadata() {
  local f="$1" meta=""
  if command -v exiftool >/dev/null 2>&1; then
    meta="$(exiftool -s -FileType -MIMEType -ImageWidth -ImageHeight -ColorMode -ColorSpace -ProfileDescription -Title -Description -Creator -Author -CreateDate -ModifyDate -DateTimeOriginal "$f" 2>/dev/null)"
    if [ -n "$meta" ]; then
      printf '## File metadata\n\n'
      printf '%s\n' "$meta" | sed -E 's/^([A-Za-z0-9_:-]+)[[:space:]]*:[[:space:]]*/- **\1:** /'
      printf '\n'
    fi
  fi
}

write_rendered_pages_markdown() {
  local asset_dir="$1" asset_rel="$2" fname="$3"
  local count=0 page="" page_base="" n=1
  count="$(rendered_count "$asset_dir")"
  printf '## Rendered pages / frames (%s)\n\n' "$count"
  find "$asset_dir" -maxdepth 1 -type f -name 'page-*.png' -size +0c | sort | while IFS= read -r page; do
    page_base="$(basename "$page")"
    printf '### Render %s\n\n' "$n"
    printf '![%s render %s](<%s/%s>)\n\n' "$fname" "$n" "$asset_rel" "$page_base"
    print_image_details "$page"
    printf '#### Text (OCR)\n\n'
    if command -v tesseract >/dev/null 2>&1; then
      tesseract "$page" stdout 2>/dev/null || printf '_OCR produced no text._\n'
    else
      printf '_tesseract not installed; run: brew install tesseract_\n'
    fi
    printf '\n'
    n=$((n + 1))
  done
}

write_structured_package_extraction() {
  local package_root="$1" kind="$2"
  if ! command -v python3 >/dev/null 2>&1; then
    printf '## Structured package extraction\n\n_python3 not found; structured JSON extraction skipped._\n\n'
    return 0
  fi
  python3 - "$package_root" "$kind" <<'PY'
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict

root = sys.argv[1]
kind = sys.argv[2]

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_ITEMS = 250
STRING_KEYS = {
    "name", "title", "label", "text", "characters", "content", "description",
    "alt", "aria-label", "placeholder", "tooltip", "value", "string", "copy"
}
TYPE_KEYS = ("type", "_class", "class", "nodeType", "node_type", "kind", "role")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".heic", ".tif", ".tiff")

def rel(path):
    return os.path.relpath(path, root)

def clean(value, limit=240):
    text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text

def md(text):
    return clean(text).replace("`", "'")

def useful_string(key, value):
    if not isinstance(value, str):
        return False
    text = clean(value, 2000)
    if not text or len(text) < 2:
        return False
    if text.startswith(("data:", "base64,")) or len(text) > 2000:
        return False
    key_l = str(key).lower()
    return key_l in STRING_KEYS or any(token in key_l for token in ("text", "name", "title", "label", "description", "character"))

def first_scalar(obj, keys):
    lower = {str(k).lower(): v for k, v in obj.items() if isinstance(v, (str, int, float, bool))}
    for key in keys:
        if key.lower() in lower:
            return lower[key.lower()]
    return ""

def add_unique(bucket, key, value):
    if key not in bucket:
        bucket[key] = value

def path_label(parts):
    out = []
    for part in parts:
        if isinstance(part, int):
            out.append(f"[{part}]")
        else:
            out.append(str(part))
    return ".".join(out) or "$"

def color_from_dict(obj):
    lower = {str(k).lower(): v for k, v in obj.items()}
    if not all(k in lower for k in ("r", "g", "b")):
        return ""
    try:
        vals = [float(lower[k]) for k in ("r", "g", "b")]
    except Exception:
        return ""
    if all(0 <= v <= 1 for v in vals):
        vals = [round(v * 255) for v in vals]
    elif all(0 <= v <= 255 for v in vals):
        vals = [round(v) for v in vals]
    else:
        return ""
    alpha = ""
    if "a" in lower:
        try:
            alpha_v = float(lower["a"])
            alpha = f", alpha {alpha_v:g}"
        except Exception:
            alpha = ""
    return "#%02X%02X%02X%s" % (vals[0], vals[1], vals[2], alpha)

json_files = 0
xml_files = 0
text_files = 0
design_text = OrderedDict()
named_objects = OrderedDict()
colors = OrderedDict()
asset_refs = OrderedDict()
json_errors = []

def walk_json(obj, source, parts):
    if isinstance(obj, dict):
        typ = first_scalar(obj, TYPE_KEYS)
        name = ""
        for key, value in obj.items():
            if useful_string(key, value):
                name = value
                break
        if name:
            object_key = (clean(name), clean(typ), source, path_label(parts))
            add_unique(named_objects, object_key, object_key)
        color = color_from_dict(obj)
        if color:
            add_unique(colors, (color, source, path_label(parts)), (color, source, path_label(parts)))
        for key, value in obj.items():
            child_parts = parts + [key]
            if useful_string(key, value):
                text_key = (clean(value, 500), source, path_label(child_parts))
                add_unique(design_text, text_key, text_key)
            if isinstance(value, str):
                cleaned = clean(value, 1000)
                if cleaned.lower().endswith(IMAGE_EXTS) or any(ext + "?" in cleaned.lower() for ext in IMAGE_EXTS):
                    add_unique(asset_refs, (cleaned, source, path_label(child_parts)), (cleaned, source, path_label(child_parts)))
                for match in re.findall(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?", cleaned):
                    add_unique(colors, (match.upper(), source, path_label(child_parts)), (match.upper(), source, path_label(child_parts)))
            walk_json(value, source, child_parts)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            walk_json(value, source, parts + [index])

for current, _, files in os.walk(root):
    for filename in files:
        if filename == ".package-image-list":
            continue
        path = os.path.join(current, filename)
        source = rel(path)
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size > MAX_FILE_BYTES:
            continue
        ext = os.path.splitext(filename)[1].lower()
        try:
            with open(path, "rb") as handle:
                raw = handle.read(MAX_FILE_BYTES + 1)
        except OSError:
            continue
        stripped = raw.lstrip()
        if stripped.startswith((b"{", b"[")):
            try:
                data = json.loads(raw.decode("utf-8-sig", errors="replace"))
                json_files += 1
                walk_json(data, source, [source])
                continue
            except Exception as exc:
                json_errors.append((source, str(exc)))
        if ext in (".svg", ".xml"):
            try:
                tree = ET.fromstring(raw.decode("utf-8", errors="replace"))
                xml_files += 1
                for element in tree.iter():
                    tag = element.tag.split("}")[-1].lower()
                    text = clean(element.text or "", 500)
                    if tag in ("text", "tspan", "title", "desc") and text:
                        key = (text, source, tag)
                        add_unique(design_text, key, key)
                    for attr_key, attr_value in element.attrib.items():
                        if useful_string(attr_key, attr_value):
                            key = (clean(attr_value, 500), source, f"@{attr_key}")
                            add_unique(design_text, key, key)
            except Exception:
                pass
        elif ext in (".txt", ".md", ".csv"):
            text_files += 1
            text = raw.decode("utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines()[:200], 1):
                line = clean(line, 500)
                if line:
                    key = (line, source, f"line {line_no}")
                    add_unique(design_text, key, key)

print("## Structured package extraction\n")
print(f"- Package type: {kind}")
print(f"- JSON-like files parsed: {json_files}")
print(f"- XML/SVG files parsed: {xml_files}")
print(f"- Text files sampled: {text_files}\n")

def print_records(title, records, formatter):
    print(f"### {title}\n")
    if not records:
        print("_None found._\n")
        return
    for index, record in enumerate(records.values()):
        if index >= MAX_OUTPUT_ITEMS:
            print(f"- _Output truncated after {MAX_OUTPUT_ITEMS} items._")
            break
        print(formatter(record))
    print()

print_records(
    "Design text strings",
    design_text,
    lambda item: f"- `{md(item[0])}` _(source: {md(item[1])}, path: {md(item[2])})_",
)
print_records(
    "Named objects, frames, and components",
    named_objects,
    lambda item: f"- `{md(item[0])}`" + (f" [{md(item[1])}]" if item[1] else "") + f" _(source: {md(item[2])}, path: {md(item[3])})_",
)
print_records(
    "Colors",
    colors,
    lambda item: f"- `{md(item[0])}` _(source: {md(item[1])}, path: {md(item[2])})_",
)
print_records(
    "Asset references found in metadata",
    asset_refs,
    lambda item: f"- `{md(item[0])}` _(source: {md(item[1])}, path: {md(item[2])})_",
)
if json_errors:
    print("### JSON parse warnings\n")
    for source, error in json_errors[:50]:
        print(f"- `{md(source)}`: {md(error)}")
    print()
PY
}

write_visual_markdown() {
  local f="$1" dest="$2" note="$3"
  local fname="" dest_dir="" asset_dir="" asset_rel=""
  fname="$(basename "$f")"
  dest_dir="$(dirname "$dest")"
  asset_rel="$fname.assets"
  asset_dir="$dest_dir/$asset_rel"
  cp "$f" "$dest_dir/$fname" 2>/dev/null || true
  {
    printf '# %s\n\n' "$fname"
    printf '_%s_\n\n' "$note"
    if render_pages "$f" "$asset_dir"; then
      print_file_metadata "$f"
      write_rendered_pages_markdown "$asset_dir" "$asset_rel" "$fname"
    else
      print_file_metadata "$f"
      printf '_No pages/frames could be rendered locally. Install ImageMagick/Ghostscript (`brew install imagemagick ghostscript`) or export this file to PDF/PNG/SVG, then rerun._\n'
    fi
  } > "$dest"
  return 0
}

write_package_markdown() {
  local f="$1" dest="$2" kind="$3"
  local fname="" dest_dir="" asset_dir="" asset_rel="" tmp="" text_file="" rel_text="" found=0
  local image_list="" image_file="" image_rel="" image_dest="" package_asset_dir="" image_count=0
  fname="$(basename "$f")"
  dest_dir="$(dirname "$dest")"
  asset_rel="$fname.assets"
  asset_dir="$dest_dir/$asset_rel"
  package_asset_dir="$asset_dir/package"
  cp "$f" "$dest_dir/$fname" 2>/dev/null || true
  {
    printf '# %s\n\n' "$fname"
    printf '_%s design/package file. This Markdown includes every rendered page/frame available locally, package image assets, package contents, and text snippets when the file is unzip-readable._\n\n' "$kind"
    if render_pages "$f" "$asset_dir"; then
      write_rendered_pages_markdown "$asset_dir" "$asset_rel" "$fname"
    fi
    print_file_metadata "$f"
    if unzip -tq "$f" >/dev/null 2>&1; then
      printf '## Package contents\n\n'
      unzip -Z1 "$f" 2>/dev/null | sed 's/^/- /' | head -n 200
      tmp="$(mktemp -d)"
      if unzip -o -q "$f" -d "$tmp" 2>/dev/null; then
        image_list="$tmp/.package-image-list"
        find "$tmp" -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' -o -iname '*.gif' -o -iname '*.svg' \) -print | sort > "$image_list"
        image_count="$(wc -l < "$image_list" 2>/dev/null | tr -d '[:space:]')"
        if [ "$image_count" -gt 0 ]; then
          printf '\n## Package image assets (%s)\n\n' "$image_count"
          mkdir -p "$package_asset_dir"
          while IFS= read -r image_file; do
            image_rel="${image_file#"$tmp"/}"
            image_dest="$package_asset_dir/$image_rel"
            mkdir -p "$(dirname "$image_dest")"
            cp "$image_file" "$image_dest" 2>/dev/null || continue
            printf '![%s](<%s/package/%s>)\n\n' "$image_rel" "$asset_rel" "$image_rel"
          done < "$image_list"
        fi
        write_structured_package_extraction "$tmp" "$kind"
        printf '\n## Raw readable snippets\n\n'
        while IFS= read -r text_file; do
          found=1
          rel_text="${text_file#"$tmp"/}"
          printf '### %s\n\n```text\n' "$rel_text"
          sed -n '1,80p' "$text_file"
          printf '\n```\n\n'
        done < <(find "$tmp" -type f \( -iname '*.json' -o -iname '*.agc' -o -iname '*.txt' -o -iname '*.xml' -o -iname '*.svg' \) -print | sort | head -n 20)
        [ "$found" -eq 0 ] && printf '_No text-like files were found inside the package._\n'
      fi
    else
      printf '## Local conversion note\n\n'
      printf '_This file is not a readable zip package here. Export it from the source app as PDF, PNG, SVG, or HTML for full Markdown conversion._\n'
    fi
  } > "$dest"
  [ -n "$tmp" ] && rm -rf "$tmp"
  return 0
}

write_onenote_markdown() {
  local f="$1" dest="$2" fname="" dest_dir=""
  fname="$(basename "$f")"
  dest_dir="$(dirname "$dest")"
  cp "$f" "$dest_dir/$fname" 2>/dev/null || true
  {
    printf '# %s\n\n' "$fname"
    printf '_Microsoft OneNote `.one`/`.onetoc2` files are proprietary binary notebook containers, and this script does not have a reliable free local reader for their page text._\n\n'
    print_file_metadata "$f"
    printf '## How to make it readable\n\n'
    printf 'Export the notebook or section from OneNote as PDF, DOCX, or HTML, put that exported file in the input folder, then rerun this converter. The exported file will be converted to searchable Markdown by the existing document handlers.\n'
  } > "$dest"
  return 0
}

# Convert ONE (non-zip) file "$1" -> markdown path "$2". Return 0 on success, nonzero on failure.
# On failure may set the global REASON to a short explanation (used in the report).
convert_one() {
  local f="$1" dest="$2"
  local fname="" stem="" ext="" dest_dir="" tmp="" out_dir="" url="" target="" meta="" rc=0
  fname="$(basename "$f")"; stem="${fname%.*}"
  ext="$(printf '%s' "${fname##*.}" | tr '[:upper:]' '[:lower:]')"
  dest_dir="$(dirname "$dest")"

  case "$ext" in
    pdf|docx|pptx|xlsx|xls|html|htm|csv)
      markitdown "$f" -o "$dest"; return $? ;;

    xlsm)   # OOXML + macros: hand to markitdown as .xlsx
      tmp="$(mktemp -d)"
      cp "$f" "$tmp/book.xlsx" && markitdown "$tmp/book.xlsx" -o "$dest"; rc=$?
      rm -rf "$tmp"; return $rc ;;

    xlsb)   # binary Excel: LibreOffice -> xlsx -> markitdown
      tmp="$(mktemp -d)"
      "$SOFFICE" --headless -env:UserInstallation="file://$tmp/lo" --convert-to xlsx --outdir "$tmp" "$f" >/dev/null 2>&1 \
        && markitdown "$tmp/${stem}.xlsx" -o "$dest"; rc=$?
      [ "$rc" -ne 0 ] && REASON="needs LibreOffice (brew install --cask libreoffice)"
      rm -rf "$tmp"; return $rc ;;

    doc|ppt)   # legacy Office: LibreOffice -> docx/pptx -> markitdown
      target="docx"; [ "$ext" = "ppt" ] && target="pptx"
      tmp="$(mktemp -d)"
      "$SOFFICE" --headless -env:UserInstallation="file://$tmp/lo" --convert-to "$target" --outdir "$tmp" "$f" >/dev/null 2>&1 \
        && markitdown "$tmp/${stem}.${target}" -o "$dest"; rc=$?
      [ "$rc" -ne 0 ] && REASON="needs LibreOffice (brew install --cask libreoffice)"
      rm -rf "$tmp"; return $rc ;;

    rtf)   # macOS textutil -> html -> markitdown
      tmp="$(mktemp -d)"
      textutil -convert html -output "$tmp/x.html" "$f" >/dev/null 2>&1 \
        && markitdown "$tmp/x.html" -o "$dest"; rc=$?
      rm -rf "$tmp"; return $rc ;;

    pages)   # Apple Pages bundle: use embedded QuickLook/Preview.pdf
      tmp="$(mktemp -d)"; rc=1
      if unzip -o -q "$f" -d "$tmp" 2>/dev/null && [ -f "$tmp/QuickLook/Preview.pdf" ]; then
        markitdown "$tmp/QuickLook/Preview.pdf" -o "$dest"; rc=$?
      else
        REASON="no embedded preview (re-save with 'Include preview in document')"
      fi
      rm -rf "$tmp"; return $rc ;;

    json)
      { echo '```json'; python3 -m json.tool "$f" 2>/dev/null || cat "$f"; echo '```'; } > "$dest"; return $? ;;

    url)
      url="$(grep -i '^[[:space:]]*URL=' "$f" 2>/dev/null | head -n1 | sed 's/^[^=]*=//' | tr -d '\r')"
      { printf '# %s\n\n' "$stem"
        if [ -n "$url" ]; then printf '[%s](%s)\n' "$url" "$url"
        else printf '_No URL field found; raw contents:_\n\n'; cat "$f"; fi
      } > "$dest"; return $? ;;

    jpg|jpeg|png)   # copy + embed image, dimensions, EXIF metadata, OCR
      cp "$f" "$dest_dir/$fname" 2>/dev/null
      { printf '# %s\n\n' "$fname"
        printf '![%s](<%s>)\n\n' "$fname" "$fname"
        if command -v sips >/dev/null 2>&1; then
          sips -g pixelWidth -g pixelHeight -g format "$f" 2>/dev/null \
            | awk '/pixelWidth/{w=$2}/pixelHeight/{h=$2}/format:/{fmt=$2}END{if(w)printf "**Image:** %s x %s px, %s\n\n", w, h, fmt}'
        fi
        if command -v exiftool >/dev/null 2>&1; then
          meta="$(exiftool -s -DateTimeOriginal -CreateDate -Make -Model -LensModel -GPSPosition -ISO -FNumber -ExposureTime -FocalLength -ImageDescription "$f" 2>/dev/null)"
          if [ -n "$meta" ]; then
            printf '## Photo metadata\n\n'
            printf '%s\n' "$meta" | sed -E 's/^([A-Za-z0-9]+)[[:space:]]*:[[:space:]]*/- **\1:** /'
            printf '\n'
          fi
        fi
        printf '## Text (OCR)\n\n'
        if command -v tesseract >/dev/null 2>&1; then
          tesseract "$f" stdout 2>/dev/null || printf '_OCR produced no text._\n'
        else
          printf '_tesseract not installed; run: brew install tesseract_\n'
        fi
      } > "$dest"; return 0 ;;

    tif|tiff|heic|heif|hei)
      write_visual_markdown "$f" "$dest" "Rendered pages/frames for Markdown viewing, plus metadata and OCR."; return $? ;;

    ai|eps)
      write_visual_markdown "$f" "$dest" "Rendered vector-art pages/artboards plus metadata and OCR. Text converted to outlines may only be available through OCR."; return $? ;;

    psd)
      write_visual_markdown "$f" "$dest" "Rendered Photoshop composite/layer scenes plus metadata and OCR. Layer semantics are included only when local tools expose them."; return $? ;;

    xd)
      write_package_markdown "$f" "$dest" "Adobe XD"; return $? ;;

    fig)
      write_package_markdown "$f" "$dest" "Figma"; return $? ;;

    one|onetoc2)
      write_onenote_markdown "$f" "$dest"; return $? ;;

    svg)   # copy + embed svg, render a companion PNG (if librsvg), extract labels
      cp "$f" "$dest_dir/$fname" 2>/dev/null
      { printf '# %s\n\n' "$fname"
        printf '![%s](<%s>)\n\n' "$fname" "$fname"
        if command -v rsvg-convert >/dev/null 2>&1 && rsvg-convert "$f" -o "$dest_dir/$fname.png" 2>/dev/null; then
          printf '![%s rendered](<%s.png>)\n\n' "$fname" "$fname"
        fi
        printf '## Text labels\n\n'
      } > "$dest"
      python3 - "$f" >> "$dest" <<'PY'
import sys, xml.etree.ElementTree as ET
texts = []
try:
    for el in ET.parse(sys.argv[1]).iter():
        tag = el.tag.split('}')[-1].lower()
        if tag in ('text', 'tspan', 'title', 'desc') and el.text and el.text.strip():
            texts.append(el.text.strip())
except Exception as e:
    print(f"_Could not parse SVG: {e}_"); sys.exit(0)
if texts:
    for t in texts: print(f"- {t}")
else:
    print("_No text labels in this vector graphic._")
PY
      return 0 ;;

    otf|ttf|ttc)   # fonts: metadata only
      python3 - "$f" > "$dest" <<'PY'
import sys, os
path = sys.argv[1]; name = os.path.basename(path)
try:
    from fontTools.ttLib import TTFont
    f = TTFont(path, fontNumber=0, lazy=True)
    def nm(i):
        try: return f['name'].getDebugName(i) or ''
        except Exception: return ''
    full = nm(4) or nm(1) or name
    rows = [("File", name), ("Family", nm(1)), ("Style", nm(2)),
            ("Full name", nm(4)), ("Version", nm(5)), ("Designer", nm(9))]
    if 'maxp' in f: rows.append(("Glyph count", str(f['maxp'].numGlyphs)))
    if 'head' in f: rows.append(("Units per em", str(f['head'].unitsPerEm)))
    print(f"# Font: {full}\n")
    print("| Field | Value |")
    print("|---|---|")
    for k, v in rows:
        if v: print(f"| {k} | {v} |")
    print("\n_Note: font files contain glyph outlines, not document text; this is metadata only._")
    f.close()
except Exception as e:
    print(f"# {name}\n\n_Could not read font metadata: {e}_")
PY
      return 0 ;;

    txt|md|markdown)
      cp "$f" "$dest"; return $? ;;

    mp4|mov|m4v|mkv|avi|webm|mp3|m4a|wav|aac|flac)   # transcribe audio/video
      out_dir="$(dirname "$dest")"
      if command -v ffprobe >/dev/null 2>&1 \
         && [ -z "$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$f" 2>/dev/null)" ]; then
        printf '# %s\n\n_Silent video: no audio track to transcribe._\n' "$fname" > "$dest"
        echo "   (no audio stream -> wrote stub)"; return 0
      fi
      if [ -n "$WHISPER_LANG" ]; then
        mlx_whisper "$f" -f txt -o "$out_dir" --model "$WHISPER_MODEL" --language "$WHISPER_LANG"
      else
        mlx_whisper "$f" -f txt -o "$out_dir" --model "$WHISPER_MODEL"
      fi
      rc=$?
      if [ "$rc" -eq 0 ] && [ -f "$out_dir/${stem}.txt" ]; then
        mv -f "$out_dir/${stem}.txt" "$dest"; return 0
      fi
      REASON="transcription failed"; return 1 ;;

    *)
      return 0 ;;   # unsupported: no output produced (walk records it as skipped)
  esac
}

# Walk every file under "$1" -> Markdown into "$2". "$3" = display-path prefix (for zips).
# Change detection is by content hash; outputs are written atomically.
walk() {
  local src="$1" out="$2" prefix="${3:-}"
  local rel="" disp="" dir="" fname="" ext="" dest_dir="" dest="" tmpdest="" zip_out="" tmp="" vhash=""
  # Prune hidden/dot directories (.git, .vscode, .DS_Store, macOS __MACOSX/._* cruft).
  find "$src" -name '.*' -prune -o -type f -print0 | while IFS= read -r -d '' f; do
    rel="${f#"$src"/}"; disp="$prefix$rel"
    dir="$(dirname "$rel")"
    fname="$(basename "$f")"
    ext="$(printf '%s' "${fname##*.}" | tr '[:upper:]' '[:lower:]')"
    dest_dir="$out/$dir"
    mkdir -p "$dest_dir"

    if [ "$ext" = "zip" ]; then
      zip_out="$dest_dir/$fname"
      vhash="$(hash_of "$f")"
      if [ "$FORCE" != "1" ] && [ -d "$zip_out" ] && [ -n "$vhash" ] && [ "$vhash" = "$(old_hash "$disp")" ]; then
        echo "== $disp  (archive unchanged, skipped)"; record skipped "$disp (archive unchanged)"; record_hash "$disp" "$vhash"; continue
      fi
      echo "-> $disp  (extracting)"
      rm -rf "$zip_out"; mkdir -p "$zip_out"
      tmp="$(mktemp -d)"
      if unzip -o -q "$f" -d "$tmp" 2>/dev/null; then
        walk "$tmp" "$zip_out" "$prefix$rel/"
        [ -n "$vhash" ] && record_hash "$disp" "$vhash"
      else
        echo "   !! failed to unzip: $disp"; record failed "$disp (unzip failed)"
      fi
      rm -rf "$tmp"
      continue
    fi

    dest="$dest_dir/$fname.md"; tmpdest="$dest_dir/.${fname}.md.partial"
    vhash="$(hash_of "$f")"
    # Skip when the output exists, is non-empty, and the source hash is unchanged.
    if [ "$FORCE" != "1" ] && [ -s "$dest" ] && [ -n "$vhash" ] && [ "$vhash" = "$(old_hash "$disp")" ]; then
      echo "== $disp  (unchanged, skipped)"; record skipped "$disp (unchanged)"; record_hash "$disp" "$vhash"; continue
    fi

    echo "-> $disp"
    REASON=""; rm -f "$tmpdest"
    if convert_one "$f" "$tmpdest"; then
      if [ -f "$tmpdest" ]; then
        if [ -s "$tmpdest" ]; then
          mv -f "$tmpdest" "$dest"                 # atomic: real .md appears only when complete
          record converted "$disp"; [ -n "$vhash" ] && record_hash "$disp" "$vhash"
        else
          rm -f "$tmpdest"; record failed "$disp (empty output)"
          echo "   !! empty output -- removed (will retry next run): $fname"
        fi
      else
        record skipped "$disp (unsupported .$ext)"   # nothing produced
      fi
    else
      rm -f "$tmpdest"; record failed "$disp (${REASON:-conversion failed})"
      echo "   !! ${REASON:-conversion failed} -- removed (will retry next run): $fname"
    fi
  done
}

[ "$FORCE" = "1" ] && echo "(FORCE=1: reconverting everything)"
echo "Converting '$SRC'  ->  '$OUT'   (change detection: content hash)"
echo
walk "$SRC" "$OUT"

# Persist this run's hashes for next time (replaces the previous manifest).
cp -f "$NEW_MANIFEST" "$OLD_MANIFEST" 2>/dev/null

# --- Final report (printed AND saved to a file in the output folder) ---------
REPORT="$OUT/_conversion_report.txt"
{
  echo "================= Conversion report ================="
  echo "When:    $(date)"
  echo "Source:  $SRC"
  echo "Output:  $OUT"
  echo "Mode:    content-hash$([ "$FORCE" = "1" ] && echo ' (FORCE)')"
  echo
  echo "Converted: $(count converted)"
  echo "Skipped:   $(count skipped)"
  echo "Failed:    $(count failed)"
  if [ -s "$STATS_DIR/skipped" ]; then
    echo; echo "Skipped files ($(count skipped)):"; sed 's/^/  == /' "$STATS_DIR/skipped"
  fi
  if [ -s "$STATS_DIR/failed" ]; then
    echo; echo "Failed files ($(count failed)):"; sed 's/^/  !! /' "$STATS_DIR/failed"
  fi
} | tee "$REPORT"
echo
echo "Output: $OUT   (report saved to $REPORT)"
