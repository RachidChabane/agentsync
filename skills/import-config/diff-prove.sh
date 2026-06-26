#!/usr/bin/env bash
# Deterministic proof for `import-config`: would applying the synthesized config/ change
# your LIVE config? It seeds a sandbox with copies of your real managed files, runs
# `agentsync apply` into the sandbox, and diffs the result against the originals. An empty
# diff means config/ faithfully reproduces your current setup — nothing lost on switch.
#
#   bash skills/import-config/diff-prove.sh
#
# Exit 0 = clean (safe to apply for real). Exit 1 = differences (config/ not faithful yet).
set -u
REPO="$(cd "$(dirname "$(dirname "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")")" && pwd)"
SAND="$(mktemp -d)"; trap 'rm -rf "$SAND"' EXIT

# Files agentsync manages, relative to $HOME. (Claude's CLI-imported MCP is checked
# separately with `claude mcp list`; this proves the file-based surface.)
VSC="Library/Application Support/Code/User/settings.json"
[ -d "$HOME/.config/Code" ] && VSC=".config/Code/User/settings.json"
FILES=(
  ".claude/settings.json" ".claude/CLAUDE.md"
  ".copilot/settings.json" ".copilot/copilot-instructions.md" ".copilot/mcp-config.json"
  ".config/opencode/opencode.json" "$VSC"
)
# Note: Claude's user-scope MCP is NOT a file — it lives in the stateful ~/.claude.json
# (CLI-imported). It's checked separately below, not via the FILES seed-and-diff.

# Seed sandbox with dereferenced copies of the real files (so apply merges into them).
for rel in "${FILES[@]}"; do
  [ -e "$HOME/$rel" ] || continue
  mkdir -p "$SAND/$(dirname "$rel")"
  cat "$HOME/$rel" > "$SAND/$rel" 2>/dev/null
done

"$REPO/bin/agentsync" apply --root "$SAND" --no-mcp-import >/dev/null 2>&1 \
  || { echo "apply into sandbox failed — check config/"; exit 1; }

fails=0
echo "diff-prove: live vs (config/ applied)"
for rel in "${FILES[@]}"; do
  [ -e "$HOME/$rel" ] || continue
  if [ ! -e "$SAND/$rel" ]; then echo "  miss  $rel (agentsync produces nothing here)"; continue; fi
  if diff -q <(cat "$HOME/$rel") <(cat "$SAND/$rel") >/dev/null 2>&1; then
    echo "  ok    $rel"
  else
    echo "  DIFF  $rel"; diff <(cat "$HOME/$rel") <(cat "$SAND/$rel") | sed 's/^/        /'
    fails=1
  fi
done

# Claude user-scope MCP (stateful ~/.claude.json) — agentsync owns the whole set (it
# prunes), so compare the intended set against what Claude actually has. A server live
# but not in config/ would be PRUNED on apply — a real loss this catches.
mcp_checked=0
if [ -f "$SAND/.claude/mcp-servers.json" ]; then
  if [ -f "$HOME/.claude.json" ]; then
    live="$(python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1])).get("mcpServers",{}),sort_keys=True,indent=2))' "$HOME/.claude.json" 2>/dev/null)"
    want="$(python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1])),sort_keys=True,indent=2))' "$SAND/.claude/mcp-servers.json" 2>/dev/null)"
    if [ -n "$live$want" ]; then
      mcp_checked=1
      if [ "$live" = "$want" ]; then echo "  ok    ~/.claude.json mcpServers (user-scope)"
      else echo "  DIFF  ~/.claude.json mcpServers (user-scope) — apply would change/prune these"
           diff <(printf '%s' "$live") <(printf '%s' "$want") | sed 's/^/        /'; fails=1; fi
    fi
  fi
fi

echo
if [ "$fails" = 0 ]; then
  echo "CLEAN — config/ reproduces your live setup; safe to apply."
  [ "$mcp_checked" = 1 ] || echo "CAVEAT: could not read ~/.claude.json — verify Claude's user-scope MCP by hand (\`claude mcp list -s user\`); it is NOT covered above."
else
  echo "DIFFERENCES — adjust config/ (or overrides.json) until clean."
fi
exit "$fails"
