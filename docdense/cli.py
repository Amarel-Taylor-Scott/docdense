"""docdense CLI — dense, chunked, LLM-ready docs, and a registry to host them.

Condense (no LLM used on raw HTML):
    docdense page   https://docs.example.com/guide            # one page → clean markdown
    docdense ingest https://docs.example.com/ --crawl -o out  # crawl → md+chunks+stats

Publish / host / consume condensed docs for the frameworks a team uses:
    docdense pack   https://flask.palletsprojects.com/ --crawl --name flask \\
                    --version 3.0 -o registry/                # build a docpack
    docdense serve  registry/ --port 8900                     # host the registry (API + UI)
    docdense list   registry/                                 # what's hosted
    docdense search "blueprint routing" registry/             # query the condensed docs
    docdense get    flask --from http://host:8900 -o flask/   # pull a docpack
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import fetch, extract, densify, corpus, docpack, registry, server, client


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
        print(json.dumps(result["stats"], indent=2))
    return 0


def _fetch_pages(a):
    if a.crawl and not os.path.isfile(a.url):
        return fetch.crawl(a.url, max_pages=a.max_pages, under_path=not a.whole_site)
    html = _load(a.url)
    return {a.url: html} if html else {}


def cmd_pack(a) -> int:
    """Publisher side: condense a doc site into a portable docpack."""
    pages = _fetch_pages(a)
    if not pages:
        print("nothing fetched", file=sys.stderr)
        return 1
    result = corpus.process(pages, do_densify=not a.no_densify, max_chars=a.max_chars)
    print(corpus.stats_report(result["stats"]), file=sys.stderr)
    out = a.out or a.name
    path = docpack.build_docpack(
        result, out, name=a.name, version=a.version, source=a.url,
        homepage=a.homepage, created=time.strftime("%Y-%m-%d"), as_zip=a.zip)
    print("packed '%s' → %s (%d chunks, %d%% fewer tokens than raw HTML)"
          % (a.name, path, result["stats"]["chunks"],
             int(result["stats"]["token_reduction"] * 100)), file=sys.stderr)
    return 0


def cmd_serve(a) -> int:
    return server.serve(a.registry, host=a.host, port=a.port)


def cmd_list(a) -> int:
    reg = registry.Registry.load(a.registry)
    fw = reg.frameworks()
    if a.json:
        print(json.dumps(fw, indent=2))
        return 0
    if not fw:
        print("no docpacks in %s" % a.registry, file=sys.stderr)
        return 0
    for f in fw:
        print("%-20s v%-8s %4d chunks  ~%s tokens  (%d%% denser than HTML)" % (
            f["name"], str(f.get("version") or "?"), f.get("chunks", 0),
            format(f.get("tokens", 0), ","),
            int((f.get("token_reduction") or 0) * 100)))
    return 0


def cmd_search(a) -> int:
    reg = registry.Registry.load(a.registry)
    res = reg.search(a.query, limit=a.limit, framework=a.framework)
    if a.json:
        print(json.dumps(res, indent=2))
        return 0
    if not res:
        print("no matches", file=sys.stderr)
        return 1
    for r in res:
        head = r["heading_path"] or r["title"] or "(untitled)"
        print("\n[%s] %s  (score %.3f · ~%s tok)"
              % (r["framework"], head, r["score"], r["est_tokens"]))
        if r["url"]:
            print("  %s" % r["url"])
        text = " ".join(r["text"].split())
        print("  " + text[:280] + ("…" if len(text) > 280 else ""))
    return 0


def cmd_get(a) -> int:
    path = client.fetch_docpack(a.url, a.name, a.out or a.name, as_zip=a.zip)
    print("pulled '%s' → %s" % (a.name, path), file=sys.stderr)
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

    p = sub.add_parser("pack", help="condense a doc site into a portable docpack")
    p.add_argument("url")
    p.add_argument("--name", required=True, help="framework/library name")
    p.add_argument("--version", help="version string (optional)")
    p.add_argument("--homepage", help="project homepage (optional)")
    p.add_argument("--crawl", action="store_true", help="follow same-section links")
    p.add_argument("--max-pages", type=int, default=40)
    p.add_argument("--whole-site", action="store_true")
    p.add_argument("--max-chars", type=int, default=4000)
    p.add_argument("--no-densify", action="store_true")
    p.add_argument("--zip", action="store_true", help="write a single .docpack zip")
    p.add_argument("-o", "--out", help="output path (default: ./<name>)")
    p.set_defaults(fn=cmd_pack)

    p = sub.add_parser("serve", help="host a registry of docpacks (HTTP API + UI)")
    p.add_argument("registry", nargs="?", default=".", help="registry directory")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8900)
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("list", help="list docpacks in a registry")
    p.add_argument("registry", nargs="?", default=".")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("search", help="search condensed docs across a registry")
    p.add_argument("query")
    p.add_argument("registry", nargs="?", default=".")
    p.add_argument("--framework", help="restrict to one framework")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("get", help="pull a docpack from a running registry")
    p.add_argument("name")
    p.add_argument("--from", dest="url", required=True, help="registry base URL")
    p.add_argument("--zip", action="store_true")
    p.add_argument("-o", "--out", help="output path (default: ./<name>)")
    p.set_defaults(fn=cmd_get)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
