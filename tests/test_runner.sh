#!/usr/bin/env bash
# Checks the commit gate + runner abstraction in a throwaway git repo (never touches a
# real repo). Covers: passing verify -> allow (0), failing verify -> block (2), no
# runner -> fail open (0), non-commit command -> ignored (0), and both stdin schemas
# (Claude .tool_input.command and Copilot .toolArgs JSON-string).
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$DIR/core/enforcement/guard-commit.sh"
fail=0
chk() { if [ "$1" = "$2" ]; then echo "  ok   $3"; else echo "  FAIL $3 (got $1 want $2)"; fail=1; fi; }

claude_in() { printf '{"cwd":"%s","tool_input":{"command":"%s"}}' "$1" "$2"; }
copilot_in() { printf '{"cwd":"%s","toolArgs":"{\\"command\\":\\"%s\\"}"}' "$1" "$2"; }

command -v make >/dev/null 2>&1 || { echo "  skip test_runner (make not installed)"; exit 0; }

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
( cd "$tmp" && git init -q && git config user.email t@t && git config user.name t )

# 1. No runner present -> fail open.
echo "$(claude_in "$tmp" "git commit -m x")" | "$GUARD"; chk $? 0 "no runner -> allow"

# 2. Makefile whose verify PASSES -> allow.
printf 'verify:\n\t@true\n' > "$tmp/Makefile"
echo "$(claude_in "$tmp" "git commit -m x")" | "$GUARD"; chk $? 0 "verify passes -> allow"

# 3. Makefile whose verify FAILS -> block (exit 2). Both schemas.
printf 'verify:\n\t@echo boom; exit 1\n' > "$tmp/Makefile"
echo "$(claude_in  "$tmp" "git commit -m x")" | "$GUARD" 2>/dev/null; chk $? 2 "verify fails -> block (claude schema)"
echo "$(copilot_in "$tmp" "git commit -m x")" | "$GUARD" 2>/dev/null; chk $? 2 "verify fails -> block (copilot schema)"

# 4. Non-commit command -> ignored even with failing verify.
echo "$(claude_in "$tmp" "git status")" | "$GUARD"; chk $? 0 "non-commit -> ignore"

# 5. No verify verb (only some other target) -> fail open.
printf 'build:\n\t@true\n' > "$tmp/Makefile"
echo "$(claude_in "$tmp" "git commit -m x")" | "$GUARD"; chk $? 0 "no verify verb -> allow"

[ "$fail" = 0 ] && echo "test_runner: PASS" || { echo "test_runner: FAIL"; exit 1; }
