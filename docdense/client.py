"""Pull a docpack from a running docdense registry (consumer side). Stdlib only."""

from __future__ import annotations

import json
import os
import urllib.request

from . import docpack as _dp


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "docdense"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def fetch_docpack(base_url: str, name: str, outpath: str, as_zip=False) -> str:
    """Download a framework's docpack from a registry server and save it locally."""
    base = base_url.rstrip("/")
    manifest = json.loads(_get("%s/api/doc/%s" % (base, name)))
    chunks_text = _get("%s/api/doc/%s/chunks" % (base, name))
    combined = _get("%s/api/doc/%s/md" % (base, name))
    if not chunks_text.endswith("\n"):
        chunks_text += "\n"

    if as_zip:
        import zipfile
        path = outpath if outpath.endswith(".docpack") else outpath + ".docpack"
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(_dp.MANIFEST, json.dumps(manifest, indent=2))
            z.writestr(_dp.CHUNKS, chunks_text)
            z.writestr(_dp.COMBINED, combined)
        return path

    os.makedirs(outpath, exist_ok=True)
    with open(os.path.join(outpath, _dp.MANIFEST), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(outpath, _dp.CHUNKS), "w", encoding="utf-8") as f:
        f.write(chunks_text)
    with open(os.path.join(outpath, _dp.COMBINED), "w", encoding="utf-8") as f:
        f.write(combined)
    return outpath
