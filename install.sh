#!/usr/bin/env bash
# One-line installer:
#   curl -fsSL https://raw.githubusercontent.com/RachidChabane/agentsync/main/install.sh | bash
#
# Clones (or updates) agentsync and runs init.sh — which detects your installed harnesses,
# creates your config/, and installs the CLIs. Re-runnable. Override the location with
# AGENTSYNC_DIR=/path.
set -euo pipefail

REPO="https://github.com/RachidChabane/agentsync.git"
DEST="${AGENTSYNC_DIR:-$HOME/dev-env/0-git/agentsync}"

command -v git >/dev/null 2>&1 || { echo "git is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }

if [ -d "$DEST/.git" ]; then
  echo "== Updating $DEST =="
  git -C "$DEST" pull --ff-only
else
  echo "== Cloning into $DEST =="
  mkdir -p "$(dirname "$DEST")"
  git clone --depth 1 "$REPO" "$DEST"
fi

cd "$DEST"
exec ./init.sh
