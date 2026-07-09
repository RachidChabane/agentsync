"""Zed adapter. Instructions only: ~/.config/zed/AGENTS.md (user) and repo AGENTS.md
(project). Zed's MCP (`context_servers`) lives inside settings.json, which Zed treats as
JSONC — comments would be destroyed by a stdlib-json merge, so we honestly don't manage
it (same graceful degradation as VS Code's missing surfaces)."""
from __future__ import annotations

from . import FileHarness


class Zed(FileHarness):
    name = "zed"
    instructions_path = ".config/zed/AGENTS.md"
