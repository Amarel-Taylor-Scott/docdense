"""Offline tests: HTML→markdown extraction, densify, cross-page dedup, chunking,
and token-savings — all deterministic, no network or LLM."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docdense import extract, densify, chunk, corpus  # noqa: E402

PAGE = """<html><head><title>Install · MyLib Docs</title>
<style>.x{color:red}</style><script>var a=1;analytics()</script></head>
<body>
<header class="site-header"><nav class="navbar">
  <a href="/">Home</a> <a href="/docs">Docs</a> <a href="/api">API</a></nav></header>
<aside class="sidebar"><ul><li><a href="/a">Alpha</a></li><li><a href="/b">Beta</a></li></ul></aside>
<main>
<h1>Installation</h1>
<p>Install MyLib with pip. It requires Python 3.9 or newer.</p>
<h2>Requirements</h2>
<ul><li>Python 3.9+</li><li>pip</li></ul>
<h2>Steps</h2>
<pre><code>pip install mylib</code></pre>
<p>Then run <code>import mylib</code> to use it.</p>
<p>Edit this page</p>
</main>
<footer class="footer">© 2026 MyLib. All rights reserved. Powered by Docs.</footer>
</body></html>"""


def test_extract_keeps_main_drops_chrome():
    title, md = extract.to_markdown(PAGE)
    assert title == "Install · MyLib Docs"
    assert "# Installation" in md and "## Requirements" in md and "## Steps" in md
    assert "pip install mylib" in md            # code block kept
    assert "import mylib" in md
    # chrome dropped:
    for junk in ("Home", "Docs", "Alpha", "Beta", "var a=1", "analytics",
                 "All rights reserved", "color:red"):
        assert junk not in md, f"leaked chrome: {junk}"


def test_densify_drops_boilerplate():
    _, md = extract.to_markdown(PAGE)
    dense = densify.densify_page(md)
    assert "Edit this page" not in dense
    assert "# Installation" in dense             # real content kept


def test_cross_page_dedup_removes_common_lines():
    pages = {f"u{i}": "# Title\n\nUnique line {}\n\nshared nav line here\n".format(i)
             for i in range(5)}
    out = densify.cross_page_dedup(pages, threshold=0.5)
    assert all("shared nav line here" not in m for m in out.values())
    assert any("Unique line 0" in out["u0"] for _ in [0])  # unique content kept


def test_chunk_headings_with_breadcrumb():
    _, md = extract.to_markdown(PAGE)
    chunks = chunk.chunk_markdown(densify.densify_page(md), url="u", title="Install",
                                  max_chars=200, min_chars=20)
    assert chunks
    paths = " ".join(c["heading_path"] for c in chunks)
    assert "Installation" in paths               # breadcrumb carries context
    assert all(c["est_tokens"] > 0 for c in chunks)


def test_pipeline_reduces_tokens():
    result = corpus.process({"http://x/install": PAGE})
    s = result["stats"]
    assert s["pages"] == 1 and s["chunks"] >= 1
    assert s["dense_tokens_est"] < s["raw_html_tokens_est"]
    assert s["token_reduction"] > 0.3           # markdown+densify is much smaller than HTML


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
