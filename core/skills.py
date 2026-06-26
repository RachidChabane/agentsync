"""Skill sourcing: resolve each configured skill to a local directory so adapters can
symlink it into a harness's skills dir. A skill in config is either:

  "name": "tier"                                          # tier only; lives elsewhere
  "name": {"tier": "...", "source": "<dir or git url>", "subpath": "skills/name"}

`source` may be a local directory (symlinked straight in) or a git URL/path (cloned into
a cache, pulled on apply). `subpath` selects a directory within the source. Stdlib +
git CLI only. Cloning happens only on `apply` (do_fetch); other verbs use the cache.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def normalize(skills_cfg: dict) -> dict:
    out = {}
    for name, v in skills_cfg.items():
        out[name] = {"tier": v} if isinstance(v, str) else dict(v)
    return out


def tiers(norm: dict) -> dict:
    return {n: d["tier"] for n, d in norm.items()}


def _slug(src: str) -> str:
    return hashlib.sha1(src.encode()).hexdigest()[:12]


def resolve(norm: dict, cache: Path, do_fetch: bool) -> dict:
    """name -> Path of the skill dir (or None if no source / unresolved)."""
    paths = {}
    for name, d in norm.items():
        src = d.get("source")
        if not src:
            paths[name] = None
            continue
        sub = d.get("subpath", "")
        local = Path(src).expanduser()
        if local.exists():                       # local directory source
            cand = local / sub if sub else local
            paths[name] = cand if cand.exists() else None
            continue
        dest = cache / _slug(src)                 # git source -> cache
        if do_fetch:
            cache.mkdir(parents=True, exist_ok=True)
            if (dest / ".git").exists():
                subprocess.run(["git", "-C", str(dest), "pull", "--ff-only", "--quiet"],
                               capture_output=True)
            else:
                subprocess.run(["git", "clone", "--depth", "1", "--quiet", src, str(dest)],
                               capture_output=True)
        cand = dest / sub if sub else dest
        paths[name] = cand if cand.exists() else None
    return paths
