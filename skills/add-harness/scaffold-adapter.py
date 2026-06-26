#!/usr/bin/env python3
"""Deterministic half of `add-harness`: scaffold a new adapter and register it. The
JUDGMENT half (reading the harness's docs and filling the stubs) is the LLM's job — this
just writes the boilerplate so no two adapters drift in structure.

  python3 skills/add-harness/scaffold-adapter.py <name>

Refuses if the adapter already exists. Writes core/adapters/<name>.py, adds the import +
registry entry to core/adapters/__init__.py, and prints the remaining (judgment) steps.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INIT = REPO / "core" / "adapters" / "__init__.py"

TEMPLATE = '''\
"""{Cls} adapter. TODO(doc): where does this harness read instructions / MCP / skills,
and what is its hook contract? Fill capabilities() and targets() from its docs."""
from __future__ import annotations

from . import Adapter
from ..targets import HookSpec, Json, Link, Merge  # drop the ones you don't use
from ..util import Ctx


class {Cls}(Adapter):
    name = "{name}"

    def capabilities(self) -> set:
        # TODO: subset of {{"instructions", "skills", "mcp", "enforcement"}}
        return set()

    def targets(self, ctx: Ctx) -> list:
        base = ctx.root / "TODO"  # the harness's config dir under $HOME
        extra_owned, extra_hooks = self._passthrough(ctx)
        return [
            # Link(base / "INSTRUCTIONS_FILE", ctx.instructions, "instructions"),
            # Json(base / "MCP_FILE", {{n: ... for n, s in ctx.servers.items()}}, "mcp"),
            # Merge(base / "settings.json",
            #       owned=[(("SOME_KEY",), VALUE)] + extra_owned,
            #       hooks=[HookSpec("EVENT", str(ctx.enforce_dir / "guard-commit.sh"),
            #                       "guard-commit.sh", matcher="...")],
            #       extra_hooks=extra_hooks, label="settings"),
            # *self._skill_links(ctx, base / "skills"),
        ]
'''


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"[a-z][a-z0-9-]*", sys.argv[1]):
        sys.exit("usage: scaffold-adapter.py <name>  (lowercase id, e.g. cursor)")
    name = sys.argv[1]
    cls = "".join(p.capitalize() for p in re.split(r"[-_]", name))
    path = REPO / "core" / "adapters" / f"{name}.py"
    if path.exists():
        sys.exit(f"refusing: {path} already exists")

    text = INIT.read_text()
    if f'"{name}"' in text or f"import {cls}\b" in text:
        sys.exit(f"refusing: {name}/{cls} already referenced in {INIT.name}")

    path.write_text(TEMPLATE.format(Cls=cls, name=name))

    # Register: add the import after the last adapter import, and into ADAPTERS.
    text = re.sub(r"(from \.vscode import VSCode\s+# noqa: E402\n)",
                  rf"\1from .{name} import {cls}          # noqa: E402\n", text, count=1)
    text = text.replace("VSCode())}", f"VSCode(), {cls}())}}")
    INIT.write_text(text)

    print(f"created {path.relative_to(REPO)} and registered {cls} in {INIT.name}\n")
    print("Now (the judgment part):")
    print("  1. Read the harness's docs: instructions-file location, MCP config format +")
    print("     path, skill/permission control, and its HOOK contract (how to run a command")
    print("     before a tool call, the stdin schema, how to block a commit).")
    print("  2. Fill capabilities() + targets() accordingly. Reuse the shared")
    print("     guard-commit.sh / session-nudge.sh for enforcement per that contract.")
    print("  3. Add a detection line in init.sh and an assertion in tests/test_apply.py.")
    print("  4. Run `make verify`.")


if __name__ == "__main__":
    main()
