"""Instruction composition: `@include` lines expand into the files they name.

An instructions source (`instructions.md`, or an `instructions.<harness>.md` variant)
may pull another markdown file in with a line that holds exactly one directive:

    @include instructions/team.md

Rules, all enforced here so every adapter renders the same text:

- The directive is a whole line starting at column 0: `@include`, whitespace, a path.
  The same text inside a fenced code block, indented, or mid-sentence is plain text.
- The path is relative to the file holding the directive and must resolve inside the
  config directory.
- One level only: an included file holds rules, never further directives. A directive
  in an included file is refused — as *cyclic* when it points back up the chain,
  otherwise as *nested*.
- The rendered text replaces the directive line with the included file's content
  (newline-terminated); nothing of the directive survives.
- A directory target is a **layer**: a directory shaped like the config dir. Its own
  `instructions.md` (optional) is spliced at the line; its JSON sources merge into the
  config (core/layers.py). Because that JSON applies to every harness, a layer can only
  be included from the shared `instructions.md`, never from a variant.

Pure text-and-path logic: no harness knowledge, no writes. Stdlib only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .util import ConfigError

DIRECTIVE_KEYWORD = "@include"
INSTRUCTIONS_FILE = "instructions.md"
VARIANT_GLOB = "instructions.*.md"

_DIRECTIVE = re.compile(rf"^{re.escape(DIRECTIVE_KEYWORD)}[ \t]+(?P<target>\S(?:.*\S)?)[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")


class IncludeError(ConfigError):
    """An `@include` directive that cannot be expanded; the message names file:line."""


@dataclass(frozen=True)
class Directive:
    line_index: int  # 0-based index into the source's lines
    target: str      # the path exactly as written

    @property
    def line_no(self) -> int:
        return self.line_index + 1


def directives(text: str) -> list[Directive]:
    """Every directive line in `text`, skipping fenced code blocks."""
    found, fence = [], None
    for i, line in enumerate(text.splitlines()):
        opener = _FENCE.match(line)
        if fence:
            if opener and opener["marker"][0] == fence[0] and len(opener["marker"]) >= len(fence):
                fence = None
            continue
        if opener:
            fence = opener["marker"]
            continue
        m = _DIRECTIVE.match(line)
        if m:
            found.append(Directive(i, m["target"]))
    return found


def expand(source: Path, config_dir: Path) -> str:
    """`source`'s text with every directive line replaced by the included file's text."""
    text = source.read_text()
    found = directives(text)
    if not found:
        return text
    lines = text.splitlines(keepends=True)
    for d in reversed(found):  # back to front, so earlier indices stay valid
        lines[d.line_index] = _included_text(source, d, config_dir)
    return "".join(lines)


def layers(config_dir: Path) -> list[Path]:
    """The layer directories the shared instructions.md includes, in directive order."""
    source = config_dir / INSTRUCTIONS_FILE
    if not source.is_file():
        return []
    found = []
    for d in directives(source.read_text()):
        target = _resolve(source, d.target)
        if target.is_dir() and target not in found:
            found.append(target)
    return found


def check(config_dir: Path) -> None:
    """Expand every instructions source in `config_dir`; raise IncludeError on the
    first directive that cannot be expanded. Lets the CLI fail before any write."""
    sources = [config_dir / INSTRUCTIONS_FILE, *sorted(config_dir.glob(VARIANT_GLOB))]
    for src in sources:
        if src.is_file():
            expand(src, config_dir)


def _included_text(source: Path, d: Directive, config_dir: Path) -> str:
    where = f"{source}:{d.line_no}"
    target = _resolve(source, d.target)
    root = config_dir.resolve()
    if not target.is_relative_to(root):
        raise IncludeError(f"{where}: {DIRECTIVE_KEYWORD} target {target} is outside "
                           f"the config directory {root}")
    if target == source.resolve():
        raise IncludeError(f"{where}: cyclic {DIRECTIVE_KEYWORD}: {source.name} includes itself")
    if target.is_dir():
        return _layer_text(source, target, where, config_dir)
    if not target.is_file():
        raise IncludeError(f"{where}: {DIRECTIVE_KEYWORD} target not found: {target}")
    body = target.read_text()
    _refuse_nested(source, target, body)
    return body if body.endswith("\n") or not body else body + "\n"


def _layer_text(source: Path, layer: Path, where: str, config_dir: Path) -> str:
    if source.resolve() != (config_dir / INSTRUCTIONS_FILE).resolve():
        raise IncludeError(f"{where}: layer {layer} can only be included from the shared "
                           f"{INSTRUCTIONS_FILE}: its config applies to every harness")
    if layer == config_dir.resolve():
        raise IncludeError(f"{where}: cyclic {DIRECTIVE_KEYWORD}: the config directory "
                           f"cannot be its own layer")
    text_file = layer / INSTRUCTIONS_FILE
    if not text_file.is_file():
        return ""
    body = text_file.read_text()
    _refuse_nested(source, text_file.resolve(), body)
    return body if body.endswith("\n") or not body else body + "\n"


def _refuse_nested(source: Path, included: Path, body: str) -> None:
    inner = directives(body)
    if not inner:
        return
    first = inner[0]
    where = f"{included}:{first.line_no}"
    if _resolve(included, first.target) in (source.resolve(), included):
        raise IncludeError(f"{where}: cyclic {DIRECTIVE_KEYWORD}: {included.name} "
                           f"includes {first.target}, which is already being expanded")
    raise IncludeError(f"{where}: nested {DIRECTIVE_KEYWORD} is not supported: "
                       f"{included.name} is itself included from {source}, so it cannot "
                       f"include {first.target}")


def _resolve(source: Path, target: str) -> Path:
    return (source.parent / target).resolve()
