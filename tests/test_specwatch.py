#!/usr/bin/env python3
"""spec_watch: HTML normalization is stable, drift is detected, fetch failures are
warnings (never drift), --update accepts the new state. Injected fetcher — no network.
Run from repo root.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import spec_watch  # noqa: E402

HTML = """<!doctype html><html><head><style>x{}</style><script>bad()</script></head>
<body><h1>MCP</h1><p>Use   <code>mcpServers</code>
in  config.</p><li>one</li></body></html>"""


def main(tmp=None):
    import tempfile
    # normalize: tags stripped, script/style dropped, whitespace collapsed, stable.
    text = spec_watch.normalize(HTML)
    assert "bad()" not in text and "x{}" not in text, "script/style leaked"
    assert "MCP\n" in text and "Use mcpServers in config." in text, text
    assert spec_watch.normalize(HTML) == text, "not deterministic"
    md = spec_watch.normalize("# Title\n\nplain  markdown\n")
    assert md == "# Title\nplain markdown\n", md

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        spec_watch.SOURCES = tmp / "sources.json"
        spec_watch.SNAPDIR = tmp / "snaps"
        spec_watch.SOURCES.write_text(
            '{"_comment": "note", "cursor": ["https://x/docs"], "zed": ["https://y/docs"]}')
        pages = {"https://x/docs": "<p>v1 format</p>", "https://y/docs": "zed doc"}

        def fetch(url):
            if url not in pages:
                raise OSError("403")
            return pages[url]

        assert spec_watch.run(update=True, fetch=fetch) == 0, "update must not report drift"
        assert spec_watch.run(update=False, fetch=fetch) == 0, "clean check right after update"
        pages["https://x/docs"] = "<p>v2 format</p>"
        assert spec_watch.run(update=False, fetch=fetch) == 1, "changed page must be drift"
        del pages["https://y/docs"]  # fetch failure: warn, never drift
        pages["https://x/docs"] = "<p>v1 format</p>"
        assert spec_watch.run(update=False, fetch=fetch) == 0, "fetch failure treated as drift"

    print("test_specwatch: PASS")


if __name__ == "__main__":
    main()
