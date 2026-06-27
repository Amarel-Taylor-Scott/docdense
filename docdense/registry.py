"""A registry: index a directory of docpacks and search across all their chunks.

This is what a company hosts internally — point it at a folder of docpacks (one
per framework the team uses) and it becomes a single searchable, condensed-docs
library that agents query instead of crawling raw doc sites. Search is a small
BM25-ish TF·IDF over chunk text with a heading/title/framework boost — no
embeddings, no dependencies.
"""

from __future__ import annotations

import math
import os
import re

from . import docpack as _dp

_WORD = re.compile(r"[a-z0-9_]+")


def _toks(s: str):
    return _WORD.findall((s or "").lower())


class Registry:
    def __init__(self):
        self.packs = {}        # name -> {manifest, chunks, path}
        self._index = []       # (name, chunk_idx, term_counts, length, head_terms)
        self._df = {}          # term -> document frequency
        self._n = 0

    @classmethod
    def load(cls, root: str) -> "Registry":
        r = cls()
        if _dp.is_docpack(root):
            r._add(root)
        elif os.path.isdir(root):
            for entry in sorted(os.listdir(root)):
                p = os.path.join(root, entry)
                if _dp.is_docpack(p):
                    r._add(p)
        r._build_index()
        return r

    def _add(self, path: str):
        data = _dp.load_docpack(path)
        name = (data["manifest"].get("name")
                or os.path.basename(path).replace(".docpack", ""))
        self.packs[name] = {"manifest": data["manifest"],
                            "chunks": data["chunks"], "path": path}

    def _build_index(self):
        self._index = []
        self._df = {}
        for name, pk in self.packs.items():
            for i, c in enumerate(pk["chunks"]):
                terms = _toks(c.get("text", ""))
                tc = {}
                for t in terms:
                    tc[t] = tc.get(t, 0) + 1
                head = set(_toks(" ".join(
                    [c.get("heading_path", ""), c.get("title", ""), name])))
                self._index.append((name, i, tc, max(1, len(terms)), head))
                for t in set(tc) | head:
                    self._df[t] = self._df.get(t, 0) + 1
        self._n = len(self._index)

    def _idf(self, t: str) -> float:
        return math.log((self._n + 1) / (1 + self._df.get(t, 0))) + 1.0

    def frameworks(self):
        return [dict(pk["manifest"], chunks=len(pk["chunks"]))
                for pk in self.packs.values()]

    def get(self, name: str):
        return self.packs.get(name)

    def search(self, query: str, limit: int = 10, framework: str = None):
        q = _toks(query)
        if not q:
            return []
        scored = []
        for name, i, tc, length, head in self._index:
            if framework and name != framework:
                continue
            s = 0.0
            for t in q:
                if t in tc:
                    s += (tc[t] / length) * self._idf(t)
                if t in head:
                    s += 1.5 * self._idf(t)
            if s > 0:
                scored.append((s, name, i))
        scored.sort(key=lambda x: -x[0])
        out = []
        for s, name, i in scored[:limit]:
            c = self.packs[name]["chunks"][i]
            out.append({
                "score": round(s, 4),
                "framework": name,
                "chunk": i,
                "heading_path": c.get("heading_path", ""),
                "url": c.get("url", ""),
                "title": c.get("title", ""),
                "est_tokens": c.get("est_tokens"),
                "text": c.get("text", ""),
            })
        return out
