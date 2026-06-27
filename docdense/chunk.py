"""Heading-aware chunking — each chunk is a section with its breadcrumb.

Docs are already structured by headings, so we split there: every chunk is one
section plus the heading path that locates it (`Guide › Install › Requirements`),
which keeps retrieval-time context without re-reading the whole page. Tiny
sections merge into their parent; oversized ones window with overlap, so chunks
land in a usable size band for embedding/LLM context.
"""

from __future__ import annotations

import re

from .densify import estimate_tokens

_H = re.compile(r"^(#{1,6})\s+(.*)$")


def _windows(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    return [text[i:i + size] for i in range(0, len(text), step)]


def chunk_markdown(md: str, *, url: str = "", title: str = "",
                   max_chars: int = 4000, min_chars: int = 350,
                   overlap: int = 300) -> list[dict]:
    # split into (level, heading, body) sections
    sections: list[tuple[int, str, list[str]]] = []
    cur = (0, title or "", [])
    for line in md.splitlines():
        m = _H.match(line)
        if m:
            sections.append(cur)
            cur = (len(m.group(1)), m.group(2).strip(), [])
        else:
            cur[2].append(line)
    sections.append(cur)

    chunks: list[dict] = []
    crumbs: list[tuple] = []        # (level, heading) stack for breadcrumbs
    pending = None                  # accumulate tiny sections

    def breadcrumb() -> str:
        return " › ".join(h for _, h in crumbs if h)

    def flush(level, heading, body):
        nonlocal pending
        body_text = "\n".join(body).strip()
        if not heading and not body_text:
            return
        crumb = breadcrumb()
        text = (f"{crumb}\n\n" if crumb else "") + \
               (f"{'#' * max(1, level)} {heading}\n\n" if heading else "") + body_text
        text = text.strip()
        # merge tiny sections forward
        if pending and len(text) < min_chars:
            pending["text"] += "\n\n" + text
            return
        if pending:
            chunks.append(pending)
            pending = None
        if len(text) < min_chars:
            pending = {"url": url, "title": title, "heading_path": crumb,
                       "heading": heading, "text": text}
            return
        for i, w in enumerate(_windows(text, max_chars, overlap)):
            chunks.append({"url": url, "title": title, "heading_path": crumb,
                           "heading": heading, "part": i, "text": w})

    for level, heading, body in sections:
        if heading:
            while crumbs and crumbs[-1][0] >= level:
                crumbs.pop()
        flush(level, heading, body)
        if heading:
            crumbs.append((level, heading))
    if pending:
        chunks.append(pending)

    for c in chunks:
        c["n_chars"] = len(c["text"])
        c["est_tokens"] = estimate_tokens(c["text"])
    return [c for c in chunks if c["text"].strip()]
