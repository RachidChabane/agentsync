"""Skill sourcing: resolve each configured skill to a local directory so adapters can
symlink it into a harness's skills dir. A skill in config is either:

  "name": "tier"                                          # tier only; lives elsewhere
  "name": {"tier": "...", "source": "<dir or git url>", "subpath": "skills/name"}

`tier` may also be a map {"default": "on", "claude": "off"}: the harness's own key wins,
else "default". Only the `tier` value takes the map form (a bare dict is the object form).

`source` may be a local directory (symlinked straight in) or a git URL/path (cloned into
a cache, pulled on apply). `subpath` selects a directory within the source. Stdlib +
git CLI only. Cloning happens only on `apply` (do_fetch); other verbs use the cache.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

DEFAULT_TIER_KEY = "default"
TIERS = {"on", "name-only", "user-invocable-only", "off"}


def normalize(skills_cfg: dict) -> dict:
    out = {}
    for name, v in skills_cfg.items():
        out[name] = {"tier": v} if isinstance(v, str) else dict(v)
    return out


def tiers(norm: dict) -> dict:
    """name -> tier spec (a tier string, or a harness -> tier map with a default)."""
    return {n: d["tier"] for n, d in norm.items()}


def effective_tier(spec, harness: str) -> str:
    return spec if isinstance(spec, str) else spec.get(harness, spec[DEFAULT_TIER_KEY])


def tiers_for(specs: dict, harness: str) -> dict:
    return {n: effective_tier(spec, harness) for n, spec in specs.items()}


def _check_spec(name: str, spec, harnesses) -> None:
    if isinstance(spec, str):
        spec = {DEFAULT_TIER_KEY: spec}
    if not isinstance(spec, dict) or DEFAULT_TIER_KEY not in spec:
        sys.exit(f"error: skill '{name}': tier must be a tier name or a map with a "
                 f"'{DEFAULT_TIER_KEY}' key")
    for key, tier in spec.items():
        if key != DEFAULT_TIER_KEY and key not in harnesses:
            sys.exit(f"error: skill '{name}': unknown harness '{key}' in tier map "
                     f"(known: {', '.join(harnesses)})")
        if tier not in TIERS:
            sys.exit(f"error: skill '{name}': unknown tier '{tier}' "
                     f"(known: {', '.join(sorted(TIERS))})")


def validate(norm: dict, harnesses) -> None:
    for name, d in norm.items():
        _check_spec(name, d.get("tier", {}), harnesses)


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
