#!/bin/bash
# Markdown links: relative Markdown links only (no Obsidian wiki-links, which
# GitHub shows as text), and every local link and #anchor resolves.
set -euo pipefail
cd "$(dirname "$0")/.."

# Tracked files only, so a local run matches CI.
md() { git ls-files -z '*.md' | xargs -0 -r "$@"; }

# [[target]] or [[target|text]] outside code; `[[ -f x ]]` in shell has a space.
wiki=$(md awk '
  FNR == 1 { fence = 0 }
  /^[ \t]*(```|~~~)/ { fence = !fence; next }
  !fence { line = $0; gsub(/`[^`]*`/, "", line); if (line ~ /\[\[[^] []/) print FILENAME ":" FNR ": " $0 }
')
if [ -n "$wiki" ]; then
  echo "$wiki"
  echo "::error::Obsidian wiki-links above; use relative Markdown links: [text](path.md)"
  exit 1
fi
docker build -q -t erpel-lychee .github/lychee >/dev/null
md docker run --rm -v "$PWD":/w:ro -w /w erpel-lychee --config lychee.toml --no-progress
