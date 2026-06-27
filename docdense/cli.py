"""docdense CLI — turn doc sites into dense, chunked, LLM-ready text (no LLM used).

    docdense page   https://docs.example.com/guide            # one page → clean markdown
    docdense ingest https://docs.example.com/guide -o out     # one page → out/ (md+chunks+stats)
    docdense ingest https://docs.example.com/ --crawl --max-pages 40 -o out
    docdense ingest file.html -o out                          # also works on a local HTML file
"""

from __future__ import annotations

import argparse
import os
import sys

from . import fetch, extract, densify, corpus


def _load(src: str) -> str:
    if os.path.isfile(src):
        return open(src, encoding="utf-8", errors="replace").read()
    html, _ = fetch.fetch(src)
    return html


def cmd_page(a) -> int:
    html = _load(a.url)
    if not html:
        print(f"could not fetch {a.url}", file=sys.stderr)
        return 1
    title, md = extract.to_markdown(html)
    if not a.no_densify:
        md = densify.densify_page(md)
    print(f"# {title}\n\n{md}" if title else md)
    return 0


def cmd_ingest(a) -> int:
    if a.crawl and not os.path.isfile(a.url):
        pages = fetch.crawl(a.url, max_pages=a.max_pages,
                            under_path=not a.whole_site)
    else:
        html = _load(a.url)
        pages = {a.url: html} if html else {}
    if not pages:
        print("nothing fetched", file=sys.stderr)
        return 1
    result = corpus.process(pages, do_densify=not a.no_densify, max_chars=a.max_chars)
    print(corpus.stats_report(result["stats"]), file=sys.stderr)
    if a.out:
        corpus.write(result, a.out)
        print(f"\nwrote {a.out}/ (combined.md, chunks.jsonl, stats.json, pages/)",
              file=sys.stderr)
    else:
        import json
        print(json.dumps(result["stats"], indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="docdense", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("page", help="one page/file → clean dense markdown")
    p.add_argument("url"); p.add_argument("--no-densify", action="store_true")
    p.set_defaults(fn=cmd_page)

    p = sub.add_parser("ingest", help="page or crawl → dense chunked corpus + stats")
    p.add_argument("url")
    p.add_argument("--crawl", action="store_true", help="follow same-section links")
    p.add_argument("--max-pages", type=int, default=30)
    p.add_argument("--whole-site", action="store_true", help="crawl whole host, not just the start path")
    p.add_argument("--max-chars", type=int, default=4000, help="target chunk size")
    p.add_argument("--no-densify", action="store_true")
    p.add_argument("-o", "--out", help="output directory")
    p.set_defaults(fn=cmd_ingest)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
