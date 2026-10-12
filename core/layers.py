"""Config layers: one `@include <dir>` line in instructions.md pulls in a whole layer.

A layer is a directory shaped like the config dir:

    layers/team/
      instructions.md   spliced at the directive line (core/instructions.py)
      mcp.json          {"servers": {...}}  merged into the base servers
      skills.json       {"skills": {...}}   merged into the base skills
      overrides.json    {harness: {...}}    merged into the base overrides

Every file is optional. Deleting the directive line removes the layer's text and
config from every harness on the next apply (the reconciler releases what it no longer
declares). Merge rules keep the result independent of which file a value came from:

- servers and skills are named entries: a name defined twice is an error;
- overrides merge recursively: objects merge key by key, lists concatenate (an item
  already present is not repeated), equal scalars agree, different scalars conflict.

Every conflict names the layer file and the key path. Stdlib only.
"""
from __future__ import annotations

import json
from pathlib import Path

from .instructions import layers
from .util import ConfigError

MCP_FILE, SKILLS_FILE, OVERRIDES_FILE = "mcp.json", "skills.json", "overrides.json"
SERVERS_KEY, SKILLS_KEY = "servers", "skills"


class LayerConflict(ConfigError):
    """A layer value that collides with the base config or an earlier layer."""


def load_json_source(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path} is not valid JSON ({e})") from e


def merge_named(base: dict, extra: dict, kind: str, source: Path) -> dict:
    """Named entries (servers, skills): each name is defined exactly once."""
    dupes = sorted(set(base) & set(extra))
    if dupes:
        raise LayerConflict(f"{source}: {kind} already defined by the base config or an "
                            f"earlier layer: {', '.join(dupes)}")
    return {**base, **extra}


def merge_deep(base, extra, source: Path, path: tuple = ()):
    """Overrides: objects merge, lists concatenate, scalars must agree."""
    if isinstance(base, dict) and isinstance(extra, dict):
        out = dict(base)
        for key, value in extra.items():
            out[key] = merge_deep(base[key], value, source, path + (key,)) \
                if key in base else value
        return out
    if isinstance(base, list) and isinstance(extra, list):
        return base + [item for item in extra if item not in base]
    if base == extra:
        return base
    raise LayerConflict(f"{source}: {'.'.join(map(str, path))} conflicts with the value "
                        f"set by the base config or an earlier layer")


def apply_layers(config_dir: Path, servers: dict, skills: dict, overrides: dict) -> tuple:
    """(servers, skills, overrides) with every included layer merged in, in order."""
    for layer in layers(config_dir):
        mcp, sk = layer / MCP_FILE, layer / SKILLS_FILE
        servers = merge_named(servers, load_json_source(mcp).get(SERVERS_KEY, {}), "servers", mcp)
        skills = merge_named(skills, load_json_source(sk).get(SKILLS_KEY, {}), "skills", sk)
        ov = layer / OVERRIDES_FILE
        overrides = merge_deep(overrides, load_json_source(ov), ov)
    return servers, skills, overrides
