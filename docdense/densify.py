"""Increase information density — deterministically, no model required.

Cleaning HTML to Markdown isn't enough; doc pages still carry low-signal lines
(`Edit this page`, `Was this helpful?`, `Previous / Next`, copyright) and, across
a crawl, the *same* nav/footer text on every page. We drop boilerplate lines,
collapse whitespace, remove link-only nav lines, and — the big win — strip blocks
that repeat across most pages. The result is fewer tokens carrying more signal.
"""

from __future__ import annotations

import re
from collections import Counter

_BOILER = re.compile(
    r"^(edit (this )?page|was this (page )?helpful|on this page|table of contents|"
    r"skip to (main )?content|back to top|previous|next|©|copyright|all rights reserved|"
    r"last updated|powered by|view source|improve this (doc|page)|report (a )?(bug|issue)|"
    r"rate this page|share (this|on)|follow us|sign in|log ?in|get started for free)\b",
    re.I)
_LINK_ONLY = re.compile(r"^\s*(\[[^\]]+\]\([^)]*\)\s*[|·,]?\s*)+$")   # a line that is only links
_NAV_BULLET = re.compile(r"^\s*-\s*\[[^\]]+\]\([^)]*\)\s*$")          # a bullet that is only a link


def densify_page(md: str, *, drop_link_lists: bool = True) -> str:
    out, prev = [], None
    for line in md.splitlines():
        s = line.strip()
        if _BOILER.match(s):
            continue
        if drop_link_lists and (_LINK_ONLY.match(s)):
            continue
        if s == prev and s != "":             # consecutive duplicate line
            continue
        out.append(line)
        prev = s
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # collapse runs of nav bullets (3+ link-only bullets in a row → drop them)
    text = re.sub(r"(?:^[ \t]*-\s*\[[^\]]+\]\([^)]*\)\s*\n){3,}", "", text, flags=re.M)
    return text.strip()


def cross_page_dedup(pages: dict[str, str], *, threshold: float = 0.5) -> dict[str, str]:
    """Remove non-heading/code lines that appear on more than ``threshold`` of pages."""
    if len(pages) < 3:
        return pages
    freq: Counter = Counter()
    for md in pages.values():
        for ln in {l.strip() for l in md.splitlines() if len(l.strip()) > 3}:
            freq[ln] += 1
    n = len(pages)
    common = {ln for ln, c in freq.items()
              if c / n >= threshold and not ln.startswith(("#", "```", "|"))}
    if not common:
        return pages
    out = {}
    for url, md in pages.items():
        kept = [l for l in md.splitlines() if l.strip() not in common]
        out[url] = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return out


def estimate_tokens(text: str) -> int:
    return max(0, len(text) // 4)            # ~4 chars/token, good enough for savings
