# docdense

> Intake documentation websites and turn them into **dense, chunked, LLM-ready
> text** — deterministically, with the stdlib, so an LLM never burns tokens
> pulling down and wading through raw HTML. Fetch → strip boilerplate → clean
> Markdown → densify → heading-aware chunks → a token-savings report.
>
> Then **host the condensed docs for the frameworks your team uses** — a tiny
> registry server agents query instead of crawling raw doc sites — and let
> framework maintainers **publish their own** docpacks.

```
fetch/crawl ─▶ extract (HTML→Markdown,    ─▶ densify (dedupe nav, drop ─▶ chunk (by heading, ─▶ chunks.jsonl
  (urllib)       drop nav/footer/scripts)     boilerplate, cross-page)     with breadcrumbs)    + combined.md + stats
                         ▲ no LLM                    ▲ no LLM                  ▲ no LLM            61–75% fewer tokens
```

## Why

Handing an LLM a raw doc page makes it pay — in tokens and attention — to parse
nav bars, cookie banners, `<script>`/`<style>`, sidebars, and `<div>` soup before
it reaches the actual content. That work is **deterministic**, so a parser should
do it, not a model. docdense extracts just the information-dense parts (headings,
code, lists, tables, prose), strips boilerplate, and pre-chunks — so the model
ingests **61–75% fewer tokens**, all signal.

Real example (a live blog/doc page):

```
$ docdense ingest https://deep-reinforce.com/ornith_1_0.html -o out
pages: 1 · chunks: 6 (avg ~409 tok)
raw HTML: ~5,964 tokens → dense: ~2,308 tokens  (61% fewer tokens for an LLM to ingest)
```

## Use it

```bash
docdense page   https://docs.example.com/guide            # one page → clean markdown (stdout)
docdense ingest https://docs.example.com/guide -o out     # → out/ (combined.md, chunks.jsonl, stats.json, pages/)
docdense ingest https://docs.example.com/ --crawl --max-pages 50 -o out   # crawl the docs section
docdense ingest local.html -o out                         # works on local HTML files too
```

`--crawl` follows links **within the same section** (the start path) on the same
host, capped by `--max-pages`; `--whole-site` widens it to the whole host.

## What you get

- **`combined.md`** — every page as clean Markdown, in order.
- **`chunks.jsonl`** — one JSON object per chunk: `{url, title, heading_path,
  text, n_chars, est_tokens}`. Ready to embed / feed a RAG store / drop into a
  prompt. Each chunk carries its **heading breadcrumb** (`Guide › Install ›
  Requirements`) so it's self-locating without the whole page.
- **`stats.json`** — pages, chunks, and the raw-HTML→dense token reduction.

## How the density is won (all deterministic)

- **Extract** (`extract.py`, stdlib `html.parser`): find the main content
  (`<main>`/`<article>`, else body), drop `script/style/nav/header/footer/aside/
  form` and any element whose class/id/role looks like chrome (menu, sidebar,
  cookie, breadcrumb, pagination, share…), and convert the rest to compact
  Markdown (headings, fenced code, lists, links, tables).
- **Densify** (`densify.py`): drop boilerplate lines (*Edit this page*, *Was this
  helpful*, *Previous/Next*, copyright), collapse whitespace, remove link-only
  nav lines, and — across a crawl — strip blocks that repeat on most pages.
- **Chunk** (`chunk.py`): split on headings, attach the breadcrumb, merge tiny
  sections, window oversized ones with overlap.

## Host condensed docs for your stack (registry)

Beyond a one-off CLI, docdense is a small **condensed-docs platform**. The unit
of distribution is a **docpack** — a directory (or single `.docpack` zip) with a
`manifest.json`, the `chunks.jsonl`, and `combined.md` for one framework.

**Publisher** — a framework's maintainers (or your platform team) condense a doc
site into a docpack:

```bash
docdense pack https://flask.palletsprojects.com/ --crawl --max-pages 60 \
        --name flask --version 3.0 -o registry/flask
docdense pack https://numpy.org/doc/stable/ --crawl --name numpy --version 2.0 \
        -o registry/numpy --zip          # a single registry/numpy.docpack
```

**Host** — point the server at a folder of docpacks; now it's one searchable,
condensed-docs library for everything your team uses:

```bash
docdense serve registry/ --port 8900
```

```
GET /api/frameworks                      what's hosted (+ token stats)
GET /api/search?q=blueprint+routing      ranked condensed chunks (TF·IDF, no embeddings)
GET /api/doc/<name>                       a framework's manifest
GET /api/doc/<name>/chunks                its chunks.jsonl (ndjson, RAG-ready)
GET /api/doc/<name>/md                    its combined dense markdown
```

An **agent** hits `/api/search?q=...` and gets back exactly the dense chunks it
needs — no crawling, no HTML parsing, no wasted tokens. Humans get a browse/search
page at `/`.

**Consume** — query from the CLI, or pull a whole docpack from a registry:

```bash
docdense search "blueprint routing" registry/      # local query
docdense list registry/
docdense get flask --from http://docs.internal:8900 -o ./flask   # pull over HTTP
```

Real run (one page → hosted → queried):

```
$ docdense pack https://deep-reinforce.com/ornith_1_0.html --name ornith --version 1.0 -o registry/ornith
raw HTML: ~5,964 tokens → dense: ~2,308 tokens  (61% fewer)
$ docdense list registry/
ornith   v1.0   6 chunks  ~2,308 tokens  (61% denser than HTML)
$ curl 'http://127.0.0.1:8900/api/search?q=reward+hacking' | jq '.results[0].heading_path'
"… › Addressing Reward Hacking in Self-improvement"
```

Everything here is stdlib (`http.server`, `urllib`, `zipfile`) — no web
framework, no vector DB, no API keys. A company can run it airgapped; the search
is a small BM25-ish TF·IDF with a heading/title boost.

## Optional: an LLM distill pass

The whole pipeline is intentionally **LLM-free** — that's the point. If you *do*
want further compression (summarize each chunk), pipe `chunks.jsonl` to your own
model; docdense gets you the clean, chunked input cheaply first so that pass is
small. (Not included by default, to keep docdense fast, offline, and free.)

## Layout

```
docdense/
  fetch.py     urllib page fetch + bounded same-section crawl
  extract.py   HTML → clean Markdown (main-content detection + boilerplate removal)
  densify.py   boilerplate/dup removal + cross-page common-block stripping + token estimate
  chunk.py     heading-aware chunks with breadcrumb context + size targets
  corpus.py    run the pipeline; write md/jsonl/stats; token-savings report
  docpack.py   the portable condensed-docs artifact (dir or .docpack zip)
  registry.py  index a folder of docpacks + TF·IDF search across their chunks
  server.py    http.server registry: JSON API for agents + browse UI for humans
  client.py    pull a docpack from a running registry
  cli.py       page / ingest / pack / serve / list / search / get
```

MIT. Stdlib only — no network libraries, no model, no API keys.
