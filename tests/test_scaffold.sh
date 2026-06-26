#!/usr/bin/env bash
# Checks add-harness's deterministic half: scaffold-adapter.py creates a registered,
# importable adapter and refuses duplicates. Restores the real __init__.py from a content
# snapshot (not git, so it never clobbers unstaged edits). Run from repo root.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
name=ztestharness
init=core/adapters/__init__.py
snap="$(mktemp)"; cp "$init" "$snap"
cleanup() { cp "$snap" "$init"; rm -f "$snap" "core/adapters/$name.py"; }
trap cleanup EXIT

python3 skills/add-harness/scaffold-adapter.py "$name" >/dev/null || { echo "FAIL: scaffold errored"; exit 1; }
python3 -c "from core.adapters import ADAPTERS; assert '$name' in ADAPTERS, ADAPTERS" \
  || { echo "FAIL: not registered/importable"; exit 1; }
python3 skills/add-harness/scaffold-adapter.py "$name" >/dev/null 2>&1 \
  && { echo "FAIL: did not refuse duplicate"; exit 1; }
echo "test_scaffold: PASS"
