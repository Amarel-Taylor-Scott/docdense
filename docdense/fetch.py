"""Fetch documentation pages — a single URL or a bounded same-domain crawl.

Deterministic and polite: stdlib urllib, depth-first within the same host (and,
by default, under the start path so a crawl of ``/docs/`` stays in the docs),
capped at ``max_pages``, skipping asset URLs. Returns raw HTML keyed by URL for
the extractor to clean — the only network step in the pipeline.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request

_HREF = re.compile(r"""<a\b[^>]*\bhref\s*=\s*["']([^"'#]+)""", re.I)
_ASSET = re.compile(r"\.(png|jpe?g|gif|svg|css|js|ico|zip|gz|pdf|woff2?|ttf|mp4|webm|json|xml)(\?|$)", re.I)


def fetch(url: str, *, timeout: int = 30) -> tuple[str, int]:
    req = urllib.request.Request(url, headers={"User-Agent": "docdense/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "")
            if "html" not in ctype and ctype:
                return "", r.status
            return r.read().decode("utf-8", "replace"), r.status
    except Exception:  # noqa: BLE001
        return "", 0


def _links(html: str, base: str) -> list[str]:
    out = []
    for href in _HREF.findall(html):
        u = urllib.parse.urljoin(base, href)
        u, _ = urllib.parse.urldefrag(u)
        if u.startswith(("http://", "https://")) and not _ASSET.search(u):
            out.append(u)
    return out


def crawl(start: str, *, max_pages: int = 30, same_domain: bool = True,
          under_path: bool = True) -> dict[str, str]:
    """Crawl from ``start`` and return {url: html}. Bounded + same-host."""
    host = urllib.parse.urlparse(start).netloc
    base_path = urllib.parse.urlparse(start).path.rsplit("/", 1)[0] + "/"
    seen, queue, pages = set(), [start], {}
    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        html, status = fetch(url)
        if not html:
            continue
        pages[url] = html
        for link in _links(html, url):
            p = urllib.parse.urlparse(link)
            if same_domain and p.netloc != host:
                continue
            if under_path and not p.path.startswith(base_path):
                continue
            if link not in seen:
                queue.append(link)
    return pages
