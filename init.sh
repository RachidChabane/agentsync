#!/usr/bin/env bash
# One-command setup. Detects which AI coding harnesses are installed, creates your
# editable config/ from the example (first run only), applies it, and installs the
# scaffold-determinism CLI on PATH. Idempotent — safe to re-run after editing config/.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

echo "== Detect installed harnesses =="
detected=()
have() { command -v "$1" >/dev/null 2>&1; }
add() { detected+=("$1"); echo "  $1"; }
{ [ -d "$HOME/.claude" ]   || have claude;   } && add claude   || true
{ [ -d "$HOME/.copilot" ]  || have copilot;  } && add copilot  || true
{ [ -d "$HOME/.config/opencode" ] || have opencode; } && add opencode || true
{ [ -d "$HOME/Library/Application Support/Code" ] || [ -d "$HOME/.config/Code" ] || have code; } \
  && add vscode || true
[ ${#detected[@]} -gt 0 ] || echo "  none detected — edit config/profile.json by hand"

echo "== Config =="
if [ ! -d config ]; then
  cp -R config.example config
  echo "  created config/ from config.example (edit it; it's yours)"
else
  echo "  config/ exists — leaving it untouched"
fi
# Write the detected harness list into profile.json (only on first run / when empty).
if [ ${#detected[@]} -gt 0 ]; then
  python3 - "$REPO/config/profile.json" "${detected[@]}" <<'PY'
import json, sys
path, harnesses = sys.argv[1], sys.argv[2:]
d = json.load(open(path)) if __import__("os").path.exists(path) else {}
d["harnesses"] = harnesses
json.dump(d, open(path, "w"), indent=2); open(path, "a").write("\n")
print(f"  profile harnesses = {', '.join(harnesses)}")
PY
fi

echo "== Make enforcement scripts executable =="
chmod +x core/enforcement/*.sh init.sh 2>/dev/null || true

echo "== Install scaffold-determinism on PATH =="
mkdir -p "$HOME/.local/bin"
ln -sfn "$REPO/core/enforcement/scaffold.sh" "$HOME/.local/bin/scaffold-determinism"
echo "  $HOME/.local/bin/scaffold-determinism -> core/enforcement/scaffold.sh"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "  note: add ~/.local/bin to PATH" ;; esac

echo "== Apply config to harnesses =="
python3 -m core.agentsync apply

echo
echo "Done. Edit config/ and re-run ./init.sh (or 'make apply') to update."
