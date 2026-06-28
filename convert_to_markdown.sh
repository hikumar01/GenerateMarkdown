#!/usr/bin/env bash
# convert_to_markdown.sh  (v4.0 - content-hash incremental, hardened)
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
#   jpg jpeg png  (image embedded + EXIF metadata + OCR)
#   svg           (embedded + rendered PNG companion + extracted text labels)
#   otf ttf ttc   (font metadata only)
#   mp4 mov m4v mkv avi webm mp3 m4a wav aac flac  (transcribed on-device)
#   zip           (extracted into a same-named folder, converted recursively)
#
# Runs 100% on your Mac -- no Claude or any other API usage.
# =============================================================================
# ONE-TIME SETUP (Terminal):
#   brew install ffmpeg tesseract
#   brew install exiftool librsvg          # OPTIONAL: photo EXIF metadata; SVG->PNG rendering
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
