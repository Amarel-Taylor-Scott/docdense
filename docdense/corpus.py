"""Run the pipeline and report the token savings.

extract → densify → cross-page dedup → chunk, then quantify what you saved: raw
HTML tokens an LLM would otherwise ingest vs. the dense chunked tokens it gets
instead. Writes a combined Markdown, a ``chunks.jsonl`` (ready for RAG/embeddings),
per-page Markdown, and ``stats.json``.
"""

from __future__ import annotations

import json
import os
import urllib.parse

from . import extract, densify, chunk


def process(pages: dict[str, str], *, do_densify: bool = True,
            max_chars: int = 4000) -> dict:
    raw_html_chars = sum(len(h) for h in pages.values())
    md_pages: dict[str, dict] = {}
    for url, html in pages.items():
        title, md = extract.to_markdown(html)
        if do_densify:
            md = densify.densify_page(md)
        md_pages[url] = {"title": title, "md": md}
    if do_densify:
        deduped = densify.cross_page_dedup({u: p["md"] for u, p in md_pages.items()})
        for u in md_pages:
            md_pages[u]["md"] = deduped[u]

    chunks = []
    for url, p in md_pages.items():
        chunks += chunk.chunk_markdown(p["md"], url=url, title=p["title"],
                                       max_chars=max_chars)

    dense_chars = sum(len(p["md"]) for p in md_pages.values())
    raw_tok, dense_tok = densify.estimate_tokens("x" * raw_html_chars), \
        densify.estimate_tokens("x" * dense_chars)
    reduction = round(1 - dense_chars / raw_html_chars, 3) if raw_html_chars else 0.0
    stats = {"pages": len(md_pages), "chunks": len(chunks),
             "raw_html_chars": raw_html_chars, "raw_html_tokens_est": raw_tok,
             "dense_chars": dense_chars, "dense_tokens_est": dense_tok,
             "token_reduction": reduction,
             "avg_chunk_tokens": round(sum(c["est_tokens"] for c in chunks) / len(chunks))
             if chunks else 0}
    return {"pages": md_pages, "chunks": chunks, "stats": stats}


def _slug(url: str) -> str:
    p = urllib.parse.urlparse(url)
    s = (p.path.strip("/") or "index").replace("/", "_")
    return (s[:60] or "index") + ".md"


def write(result: dict, outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)
    pdir = os.path.join(outdir, "pages")
    os.makedirs(pdir, exist_ok=True)
    combined = []
    for url, p in result["pages"].items():
        with open(os.path.join(pdir, _slug(url)), "w", encoding="utf-8") as f:
            f.write(f"<!-- {url} -->\n# {p['title']}\n\n{p['md']}\n")
        combined.append(f"# {p['title']}\n<!-- {url} -->\n\n{p['md']}")
    with open(os.path.join(outdir, "combined.md"), "w", encoding="utf-8") as f:
        f.write("\n\n---\n\n".join(combined))
    with open(os.path.join(outdir, "chunks.jsonl"), "w", encoding="utf-8") as f:
        for c in result["chunks"]:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(os.path.join(outdir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(result["stats"], f, indent=2)


def stats_report(s: dict) -> str:
    return (f"pages: {s['pages']}  ·  chunks: {s['chunks']}  "
            f"(avg ~{s['avg_chunk_tokens']} tok)\n"
            f"raw HTML: ~{s['raw_html_tokens_est']:,} tokens  →  "
            f"dense: ~{s['dense_tokens_est']:,} tokens  "
            f"({int(s['token_reduction']*100)}% fewer tokens for an LLM to ingest)")
