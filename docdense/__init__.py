"""docdense — intake documentation websites and turn them into dense, chunked,
LLM-ready text, deterministically (stdlib only) so an LLM never burns tokens on
raw HTML.

    from docdense import fetch, corpus
    pages = fetch.crawl("https://docs.example.com/", max_pages=40)
    result = corpus.process(pages)          # extract → densify → chunk
    print(corpus.stats_report(result["stats"]))
"""

from . import fetch, extract, densify, chunk, corpus

__all__ = ["fetch", "extract", "densify", "chunk", "corpus"]
__version__ = "0.1.0"
