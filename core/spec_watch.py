"""Deterministic layer of spec-sync: fetch each harness's primary-source docs, normalize
to plain text, and diff against committed snapshots (docs/spec-snapshots/). A changed
spec page exits 1 with the diff — the judgment step (does it affect an adapter?) is
deliberately NOT here; a human or agent reads the diff and PRs the fix.

  python3 -m core.spec_watch            # check: exit 1 if any source drifted
  python3 -m core.spec_watch --update   # accept the current state as the new snapshots

Fetch failures (bot-blocking, outages) are warnings, never drift — a missing page says
nothing about the format. Stdlib only.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCES = REPO / "docs" / "spec-sources.json"
SNAPDIR = REPO / "docs" / "spec-snapshots"
UA = {"User-Agent": "Mozilla/5.0 (agentsync spec-watch; +https://github.com/RachidChabane/agentsync)"}
BLOCKS = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "br", "section", "article"}


class _Text(HTMLParser):
    """Tag-stripper: collect visible text, block-level tags become line breaks."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag in BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag in BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            # source newlines inside a block are just whitespace in HTML
            self.parts.append(re.sub(r"\s+", " ", data))


def normalize(raw: str) -> str:
    """HTML (or markdown, passed through) -> stable plain text: one block per line,
    collapsed whitespace — so a diff shows content changes, not markup churn."""
    if "<html" in raw[:2000].lower() or "<!doctype" in raw[:200].lower():
        p = _Text()
        p.feed(raw)
        raw = "".join(p.parts)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw.splitlines()]
    return "\n".join(ln for ln in lines if ln) + "\n"


def _fetch(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _slug(harness: str, url: str) -> str:
    return f"{harness}--" + re.sub(r"[^a-z0-9]+", "-", url.split("://", 1)[-1].lower()).strip("-") + ".txt"


def run(update: bool, fetch=_fetch) -> int:
    sources = json.loads(SOURCES.read_text())
    drift = False
    for harness, urls in sources.items():
        if not isinstance(urls, list):  # e.g. the "_comment" string
            continue
        for url in urls:
            snap = SNAPDIR / _slug(harness, url)
            try:
                new = normalize(fetch(url))
            except Exception as e:
                print(f"warn: {harness}: could not fetch {url} ({e}) — skipped")
                continue
            old = snap.read_text() if snap.exists() else None
            if old == new:
                print(f"ok: {harness}: {url}")
                continue
            if update:
                SNAPDIR.mkdir(parents=True, exist_ok=True)
                snap.write_text(new)
                print(f"updated: {harness}: {url}")
                continue
            drift = True
            print(f"DRIFT: {harness}: {url}")
            if old is not None:
                d = list(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                              fromfile="snapshot", tofile="live"))
                sys.stdout.writelines(d[:200])
                if len(d) > 200:
                    print(f"... ({len(d) - 200} more diff lines)")
            else:
                print("  (no snapshot yet — run --update to create it)")
    if drift:
        print("\nspec drift — read the diffs, update the affected adapter(s), then "
              "`python3 -m core.spec_watch --update`.")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(run(update="--update" in sys.argv))
