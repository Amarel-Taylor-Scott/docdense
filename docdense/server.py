"""Serve a docpack registry over HTTP — stdlib only, read-only.

JSON API (for agents / RAG):
    GET /api/frameworks                    list hosted frameworks + stats
    GET /api/search?q=...&framework=&limit= ranked condensed chunks
    GET /api/doc/<name>                    one framework's manifest
    GET /api/doc/<name>/chunks             its chunks.jsonl (ndjson)
    GET /api/doc/<name>/md                 its combined dense markdown
Plus a minimal HTML index at ``/`` so a human can browse and search.
"""

from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from . import docpack as _dp
from . import registry as _reg


def make_handler(reg):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False, indent=2))

        def do_GET(self):
            u = urlparse(self.path)
            path, q = u.path, parse_qs(u.query)

            if path == "/":
                return self._send(200, _index_html(reg), "text/html")
            if path == "/api/frameworks":
                return self._json(200, {"frameworks": reg.frameworks()})
            if path == "/api/search":
                query = (q.get("q") or [""])[0]
                fw = (q.get("framework") or [None])[0]
                try:
                    lim = int((q.get("limit") or ["10"])[0])
                except ValueError:
                    lim = 10
                return self._json(200, {"query": query,
                                        "results": reg.search(query, lim, fw)})
            if path.startswith("/api/doc/"):
                rest = path[len("/api/doc/"):]
                name = rest.split("/")[0]
                pk = reg.get(name)
                if not pk:
                    return self._json(404, {"error": "framework not found"})
                if rest.endswith("/chunks"):
                    body = "".join(json.dumps(c, ensure_ascii=False) + "\n"
                                   for c in pk["chunks"])
                    return self._send(200, body, "application/x-ndjson")
                if rest.endswith("/md"):
                    data = _dp.load_docpack(pk["path"])
                    return self._send(200, data["combined"], "text/markdown")
                return self._json(200, dict(pk["manifest"],
                                            chunks=len(pk["chunks"])))
            return self._json(404, {"error": "unknown path"})

        do_HEAD = do_GET

    return Handler


def _index_html(reg) -> str:
    items = []
    for f in reg.frameworks():
        name = html.escape(f["name"])
        items.append(
            '<li><a href="/api/doc/%s">%s</a> — v%s · %d chunks · ~%s tokens '
            '(<a href="/api/doc/%s/md">md</a>, '
            '<a href="/api/doc/%s/chunks">chunks</a>)</li>' % (
                quote(f["name"]), name, html.escape(str(f.get("version") or "?")),
                f.get("chunks", 0), format(f.get("tokens", 0), ","),
                quote(f["name"]), quote(f["name"])))
    return (
        "<!doctype html><meta charset=utf-8><title>docdense registry</title>"
        "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:760px;"
        "margin:40px auto;padding:0 16px}a{color:#06c}</style>"
        "<h1>docdense registry</h1>"
        "<p>Condensed, LLM-ready documentation. Agents query "
        "<code>/api/search?q=</code>; humans browse below.</p>"
        "<form action=/api/search>"
        "<input name=q placeholder='search the docs' size=40> "
        "<button>search</button></form>"
        "<ul>" + "".join(items) + "</ul>")


def serve(root: str, host: str = "127.0.0.1", port: int = 8900) -> int:
    reg = _reg.Registry.load(root)
    httpd = ThreadingHTTPServer((host, port), make_handler(reg))
    print("docdense registry: %d framework(s) on http://%s:%d  (Ctrl-C to stop)"
          % (len(reg.packs), host, port))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
