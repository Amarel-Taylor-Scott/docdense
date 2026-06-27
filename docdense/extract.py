"""HTML → clean Markdown, deterministically (stdlib ``html.parser`` only).

This is the step that normally wastes an LLM's tokens: pull a doc page and the
LLM has to wade through nav bars, scripts, cookie banners, and `<div>` soup. We
do it with a parser instead — drop boilerplate tags/sections, find the main
content (`<main>`/`<article>` or the body minus chrome), and emit compact
Markdown that keeps the *information-dense* parts: headings, code blocks, lists,
links, tables. No model, no tokens.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from html import unescape

# Tags whose entire subtree is noise for documentation content.
_DROP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside",
              "form", "button", "svg", "iframe", "template", "head", "dialog"}
# class/id substrings that mark chrome rather than content.
_DROP_ATTR = re.compile(
    r"\b(nav|menu|sidebar|side-bar|footer|header|breadcrumb|toc|table-of-contents|"
    r"cookie|consent|banner|advert|\bads?\b|search|pagination|pager|edit-(this|page)|"
    r"skip-link|social|share|subscribe|newsletter|announce)\b", re.I)
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_VOID = {"br", "img", "hr", "input", "meta", "link", "source", "col"}
_MAIN = {"main", "article"}


class _MD(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[tuple] = []        # (tag, is_drop)
        self.drop = 0                       # depth of dropped subtree
        self.in_pre = False
        self.list_depth = 0
        self.href = None
        self.title = ""
        self._main_spans: list[tuple] = []  # (start_index, end_index) in self.out
        self._main_open = []                # stack indices where a <main>/<article> opened

    # -- helpers ----------------------------------------------------------
    def _emit(self, s: str):
        if not self.drop:
            self.out.append(s)

    def _is_drop(self, tag, attrs):
        if tag in _DROP_TAGS:
            return True
        ad = dict(attrs)
        blob = f"{ad.get('class','')} {ad.get('id','')} {ad.get('role','')}"
        if ad.get("role") in ("navigation", "banner", "contentinfo", "search", "complementary"):
            return True
        return bool(_DROP_ATTR.search(blob))

    # -- tags -------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        drop = self._is_drop(tag, attrs)
        if tag not in _VOID:
            self.stack.append((tag, drop))
        if drop:
            self.drop += 1
            return
        if self.drop:
            return
        if tag in _MAIN:
            self._main_open.append(len(self.out))
        if tag in _HEADINGS:
            self._emit("\n\n" + "#" * _HEADINGS[tag] + " ")
        elif tag == "p":
            self._emit("\n\n")
        elif tag in ("ul", "ol"):
            self.list_depth += 1
        elif tag == "li":
            self._emit("\n" + "  " * max(0, self.list_depth - 1) + "- ")
        elif tag == "pre":
            self.in_pre = True
            self._emit("\n\n```\n")
        elif tag == "code" and not self.in_pre:
            self._emit("`")
        elif tag == "a":
            self.href = dict(attrs).get("href")
            self._emit("[")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "blockquote":
            self._emit("\n\n> ")
        elif tag in ("br", "hr"):
            self._emit("\n" if tag == "br" else "\n\n---\n\n")
        elif tag in ("tr",):
            self._emit("\n")
        elif tag in ("td", "th"):
            self._emit(" | ")

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and not self.drop:
            self._emit("\n")

    def handle_endtag(self, tag):
        # unwind the stack to the matching open tag, tracking dropped regions
        was_drop = False
        while self.stack:
            t, d = self.stack.pop()
            if d:
                self.drop = max(0, self.drop - 1)
            if t == tag:
                was_drop = d
                break
        if was_drop or self.drop:
            return
        if tag in _MAIN and self._main_open:
            self._main_spans.append((self._main_open.pop(), len(self.out)))
        if tag in _HEADINGS:
            self._emit("\n")
        elif tag == "pre":
            self.in_pre = False
            self._emit("\n```\n")
        elif tag == "code" and not self.in_pre:
            self._emit("`")
        elif tag == "a":
            href = self.href
            self.href = None
            self._emit(f"]({href})" if href and not href.startswith("#") else "]")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag in ("ul", "ol"):
            self.list_depth = max(0, self.list_depth - 1)

    def handle_data(self, data):
        if self.drop:
            return
        if self.in_pre:
            self.out.append(data)
        else:
            t = re.sub(r"[ \t\r\f]+", " ", data)
            if t.strip() or t == " ":
                self.out.append(t)

    # -- result -----------------------------------------------------------
    def markdown(self) -> str:
        if self._main_spans:               # prefer the largest <main>/<article> region
            s, e = max(self._main_spans, key=lambda se: se[1] - se[0])
            text = "".join(self.out[s:e])
        else:
            text = "".join(self.out)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def to_markdown(html: str) -> tuple[str, str]:
    """Return (title, clean_markdown) for a documentation HTML page."""
    title = ""
    m = _TITLE.search(html or "")
    if m:
        title = unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    p = _MD()
    try:
        p.feed(html or "")
    except Exception:  # noqa: BLE001 — never crash on malformed markup
        pass
    return title, p.markdown()
