#!/usr/bin/env bash
# convert_to_markdown.sh
# ----------------------------------------------------------------------------
# Batch-convert a mixed-format project folder to Markdown, locally and FREE.
# Handles: pdf, docx, pptx, xlsx/xls, doc/ppt (legacy), txt/md, html/csv,
#          and video/audio files (transcribed on-device).
# Mirrors the input folder structure into the output folder.
# Runs 100% on your Mac — no Claude or any other API usage.
#
# ----------------------------------------------------------------------------
# ONE-TIME SETUP (run these once in Terminal):
#
#   # 1. Homebrew (skip if you already have it):
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
#
#   # 2. System tools:
#   brew install ffmpeg                      # needed to read audio out of videos
#   brew install --cask libreoffice          # ONLY if you have legacy .doc / .ppt files
#
#   # 3. Python tools in an isolated env (keeps your system clean):
#   python3 -m venv ~/md-convert-env
#   source ~/md-convert-env/bin/activate
#   pip install --upgrade pip
#   pip install 'markitdown[pdf,docx,pptx,xlsx]' mlx-whisper
#
# ----------------------------------------------------------------------------
# RUN IT:
#   source ~/md-convert-env/bin/activate     # do this each new Terminal session
#   chmod +x convert_to_markdown.sh          # once, to make it executable
#   ./convert_to_markdown.sh "/path/to/project" "/path/to/output"
# ----------------------------------------------------------------------------

set -uo pipefail   # note: NOT -e, so one bad file won't abort the whole batch

SRC="${1:?Usage: ./convert_to_markdown.sh <input_folder> <output_folder>}"
OUT="${2:?Usage: ./convert_to_markdown.sh <input_folder> <output_folder>}"
SRC="${SRC%/}"; OUT="${OUT%/}"

# --- Settings you can tweak -------------------------------------------------
# Whisper model: turbo gives the best quality/speed on Apple Silicon.
# On an 8GB Air or for faster runs, switch to: mlx-community/whisper-small-mlx
WHISPER_MODEL="mlx-community/whisper-large-v3-turbo"
# Language hint for transcription. Leave empty ("") to auto-detect.
WHISPER_LANG="en"
# ---------------------------------------------------------------------------

# Locate LibreOffice (only used for legacy .doc/.ppt)
SOFFICE="$(command -v soffice || echo /Applications/LibreOffice.app/Contents/MacOS/soffice)"

mkdir -p "$OUT"
echo "Converting '$SRC'  ->  '$OUT'"
echo

find "$SRC" -type f ! -name '.*' -print0 | while IFS= read -r -d '' f; do
  rel="${f#"$SRC"/}"                 # path relative to the source root
  dir="$(dirname "$rel")"
  base="$(basename "${f%.*}")"
  ext="$(printf '%s' "${f##*.}" | tr '[:upper:]' '[:lower:]')"
  dest_dir="$OUT/$dir"
  mkdir -p "$dest_dir"
  dest="$dest_dir/$base.md"

  echo "-> $rel"

  case "$ext" in
    pdf|docx|pptx|xlsx|xls|html|htm|csv)
      markitdown "$f" -o "$dest" \
        || echo "   !! markitdown failed for: $rel" ;;

    doc|ppt)   # legacy binary Office -> convert to modern format, then markitdown
      target_ext="docx"; [ "$ext" = "ppt" ] && target_ext="pptx"
      tmp="$(mktemp -d)"
      "$SOFFICE" --headless --convert-to "$target_ext" --outdir "$tmp" "$f" >/dev/null 2>&1 \
        && markitdown "$tmp/$base.$target_ext" -o "$dest" \
        || echo "   !! legacy convert failed (is LibreOffice installed?): $rel"
      rm -rf "$tmp" ;;

    txt|md|markdown)
      cp "$f" "$dest" ;;

    mp4|mov|m4v|mkv|avi|webm|mp3|m4a|wav|aac|flac)   # video/audio -> transcript
      lang_flag=()
      [ -n "$WHISPER_LANG" ] && lang_flag=(--language "$WHISPER_LANG")
      if mlx_whisper "$f" -f txt -o "$dest_dir" --model "$WHISPER_MODEL" "${lang_flag[@]}"; then
        # mlx_whisper writes "<base>.txt"; rename it to "<base>.md"
        [ -f "$dest_dir/$base.txt" ] && mv -f "$dest_dir/$base.txt" "$dest"
      else
        echo "   !! transcription failed for: $rel"
      fi ;;

    *)
      echo "   (skipped: unsupported .$ext)" ;;
  esac
done

echo
echo "Done. Markdown written to: $OUT"
echo "Tip: same-named files of different types in one folder (e.g. report.pdf + report.docx)"
echo "     will both map to report.md — rename one beforehand if that applies to you."
