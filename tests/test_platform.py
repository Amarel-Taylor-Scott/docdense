"""Offline tests for the docpack format and the registry/search. No network."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docdense import docpack, registry  # noqa: E402


def _result(name, chunks):
    """Build a corpus-style result dict for one synthetic page."""
    md = "\n\n".join(c["text"] for c in chunks)
    pages = {"http://x/%s" % name: {"title": name, "md": md}}
    stats = {"pages": 1, "chunks": len(chunks),
             "raw_html_chars": len(md) * 5, "raw_html_tokens_est": len(md) * 5 // 4,
             "dense_chars": len(md), "dense_tokens_est": len(md) // 4,
             "token_reduction": 0.8,
             "avg_chunk_tokens": sum(c["est_tokens"] for c in chunks) // len(chunks)}
    return {"pages": pages, "chunks": chunks, "stats": stats}


def _chunk(url, title, heading, text):
    return {"url": url, "title": title, "heading_path": heading,
            "text": text, "n_chars": len(text), "est_tokens": max(1, len(text) // 4)}


FLASK = [
    _chunk("http://f/routing", "Flask", "Flask › Routing",
           "Use the route decorator to bind a function to a URL. Blueprints group routes."),
    _chunk("http://f/install", "Flask", "Flask › Installation",
           "Install Flask with pip. It needs Python 3.8 or newer."),
]
NUMPY = [
    _chunk("http://n/array", "NumPy", "NumPy › Arrays",
           "Create an ndarray with np.array. Arrays are homogeneous and fast."),
]


def test_docpack_dir_roundtrip():
    d = tempfile.mkdtemp(prefix="dp-")
    out = os.path.join(d, "flask")
    path = docpack.build_docpack(_result("flask", FLASK), out, name="flask",
                                 version="3.0", source="http://f/")
    assert docpack.is_docpack(path)
    loaded = docpack.load_docpack(path)
    assert loaded["manifest"]["name"] == "flask"
    assert loaded["manifest"]["version"] == "3.0"
    assert loaded["manifest"]["chunks"] == 2
    assert len(loaded["chunks"]) == 2
    assert "Blueprints" in loaded["combined"]


def test_docpack_zip_roundtrip():
    d = tempfile.mkdtemp(prefix="dp-")
    out = os.path.join(d, "numpy")
    path = docpack.build_docpack(_result("numpy", NUMPY), out, name="numpy",
                                 version="2.0", as_zip=True)
    assert path.endswith(".docpack")
    assert docpack.is_docpack(path)
    loaded = docpack.load_docpack(path)
    assert loaded["manifest"]["name"] == "numpy"
    assert len(loaded["chunks"]) == 1


def test_registry_indexes_multiple_packs():
    d = tempfile.mkdtemp(prefix="reg-")
    docpack.build_docpack(_result("flask", FLASK), os.path.join(d, "flask"),
                          name="flask", version="3.0")
    docpack.build_docpack(_result("numpy", NUMPY), os.path.join(d, "numpy"),
                          name="numpy", version="2.0", as_zip=True)
    reg = registry.Registry.load(d)
    names = sorted(f["name"] for f in reg.frameworks())
    assert names == ["flask", "numpy"]
    assert reg.get("flask")["manifest"]["version"] == "3.0"


def test_registry_search_ranks_relevant_chunk_first():
    d = tempfile.mkdtemp(prefix="reg-")
    docpack.build_docpack(_result("flask", FLASK), os.path.join(d, "flask"),
                          name="flask")
    docpack.build_docpack(_result("numpy", NUMPY), os.path.join(d, "numpy"),
                          name="numpy")
    reg = registry.Registry.load(d)
    res = reg.search("blueprint routing url", limit=5)
    assert res, "expected matches"
    assert res[0]["framework"] == "flask"
    assert "Routing" in res[0]["heading_path"]
    # framework filter
    only = reg.search("array", framework="numpy")
    assert all(r["framework"] == "numpy" for r in only)
    assert only and "Arrays" in only[0]["heading_path"]


def test_search_empty_query_returns_nothing():
    d = tempfile.mkdtemp(prefix="reg-")
    docpack.build_docpack(_result("flask", FLASK), os.path.join(d, "flask"),
                          name="flask")
    reg = registry.Registry.load(d)
    assert reg.search("") == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print("\n%d passed" % len(fns))
