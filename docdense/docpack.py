"""docpack — a portable, condensed-docs artifact for one framework / library.

A **docpack** is the unit of distribution: either a directory or a single
``.docpack`` (a zip) containing

    manifest.json   name, version, source, homepage, stats, chunk count
    chunks.jsonl    the dense, heading-aware chunks (RAG / embedding ready)
    combined.md     the whole dense doc as one Markdown file

A framework's maintainers build one with ``docdense pack`` (publisher side); a
company hosts a directory of many and serves them with ``docdense serve``
(registry side); an agent pulls one with ``docdense get`` (consumer side).
Everything below is stdlib only.
"""

from __future__ import annotations

import json
import os
import zipfile

MANIFEST = "manifest.json"
CHUNKS = "chunks.jsonl"
COMBINED = "combined.md"
FORMAT = "docpack/1"


def _combined_md(result: dict) -> str:
    parts = []
    for url, p in result["pages"].items():
        parts.append("# %s\n<!-- %s -->\n\n%s" % (p["title"], url, p["md"]))
    return "\n\n---\n\n".join(parts)


def build_manifest(result: dict, *, name, version=None, source=None,
                   homepage=None, created=None) -> dict:
    s = result["stats"]
    return {
        "format": FORMAT,
        "name": name,
        "version": version,
        "source": source,
        "homepage": homepage,
        "created": created,          # caller stamps; kept optional for determinism
        "pages": s["pages"],
        "chunks": s["chunks"],
        "tokens": s["dense_tokens_est"],
        "raw_html_tokens": s["raw_html_tokens_est"],
        "token_reduction": s["token_reduction"],
        "avg_chunk_tokens": s["avg_chunk_tokens"],
    }


def build_docpack(result: dict, outpath: str, *, name, version=None, source=None,
                  homepage=None, created=None, as_zip=False) -> str:
    """Write a docpack (dir, or a ``.docpack`` zip if ``as_zip``). Returns the path."""
    manifest = build_manifest(result, name=name, version=version, source=source,
                              homepage=homepage, created=created)
    chunks = result["chunks"]
    combined = _combined_md(result)
    chunks_text = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks)

    if as_zip:
        path = outpath if outpath.endswith(".docpack") else outpath + ".docpack"
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(MANIFEST, json.dumps(manifest, indent=2))
            z.writestr(CHUNKS, chunks_text)
            z.writestr(COMBINED, combined)
        return path

    os.makedirs(outpath, exist_ok=True)
    with open(os.path.join(outpath, MANIFEST), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(outpath, CHUNKS), "w", encoding="utf-8") as f:
        f.write(chunks_text)
    with open(os.path.join(outpath, COMBINED), "w", encoding="utf-8") as f:
        f.write(combined)
    return outpath


def load_docpack(path: str) -> dict:
    """Load a docpack dir or ``.docpack`` zip → {manifest, chunks, combined}."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            manifest = json.loads(z.read(MANIFEST).decode("utf-8"))
            names = z.namelist()
            chunks = ([json.loads(ln) for ln in
                       z.read(CHUNKS).decode("utf-8").splitlines() if ln.strip()]
                      if CHUNKS in names else [])
            combined = z.read(COMBINED).decode("utf-8") if COMBINED in names else ""
        return {"manifest": manifest, "chunks": chunks, "combined": combined}

    if os.path.isdir(path):
        with open(os.path.join(path, MANIFEST), encoding="utf-8") as f:
            manifest = json.load(f)
        chunks = []
        cp = os.path.join(path, CHUNKS)
        if os.path.isfile(cp):
            with open(cp, encoding="utf-8") as f:
                chunks = [json.loads(ln) for ln in f if ln.strip()]
        combined = ""
        mp = os.path.join(path, COMBINED)
        if os.path.isfile(mp):
            combined = open(mp, encoding="utf-8").read()
        return {"manifest": manifest, "chunks": chunks, "combined": combined}

    raise FileNotFoundError("not a docpack: %s" % path)


def is_docpack(path: str) -> bool:
    if os.path.isdir(path):
        return os.path.isfile(os.path.join(path, MANIFEST))
    if zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as z:
                return MANIFEST in z.namelist()
        except Exception:
            return False
    return False
