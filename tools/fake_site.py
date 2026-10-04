"""A stand-in for the website's toolApi function, with the same contract.

Used by the tests and for trying the tool without touching the real site:
    python tools/fake_site.py 8765        (token: test-token-0123456789abcdefgh)
then point the tool at it with DNPS_SITE_BASE=http://127.0.0.1:8765
"""
from __future__ import annotations

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "test-token-0123456789abcdefgh"
REQUIRED = {"Ebook": ("title", "slug", "description", "price", "cover_image"),
            "Product": ("title", "slug", "category", "price", "images", "description", "spring_url")}


class FakeSite:
    def __init__(self, port: int = 0):
        self.records: dict[str, list[dict]] = {"Ebook": [], "Product": []}
        self.files: list[dict] = []
        self.fail_upload = False
        site = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, status, data):
                body = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):  # noqa: N802
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if not self.path.endswith("/functions/toolApi"):
                    return self._json(404, {"error": "not found"})
                if self.headers.get("X-Tool-Token") != TOKEN:
                    return self._json(401, {"error": "Unauthorized"})
                ctype = self.headers.get("Content-Type") or ""
                if ctype.startswith("multipart/form-data"):
                    if site.fail_upload:
                        return self._json(413, {"error": "too large"})
                    name = re.search(rb'name="file"; filename="([^"]*)"', raw).group(1).decode()
                    private = b'name="private"\r\n\r\n1' in raw
                    boundary = ctype.split("boundary=")[1].encode()
                    part = next(p for p in raw.split(b"--" + boundary) if b'name="file"' in p)
                    data = part.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0]
                    site.files.append({"name": name, "private": private, "size": len(data), "head": data[:4]})
                    n = len(site.files)
                    if private:
                        return self._json(200, {"file_uri": f"mp/private/app/{n}_{name}"})
                    return self._json(200, {"file_url": f"https://media.base44.com/images/public/app/{n}_{name}"})
                body = json.loads(raw or b"{}")
                action = body.get("action")
                if action == "ping":
                    return self._json(200, {"ok": True, "site": "Dark Network (giả lập)"})
                entity = body.get("entity")
                if entity not in site.records:
                    return self._json(400, {"error": "Unknown entity"})
                rows = site.records[entity]
                if action == "list":
                    return self._json(200, {"items": [{k: r.get(k) for k in ("id", "title", "slug", "status")} for r in rows]})
                if action == "upsert":
                    data = body.get("data") or {}
                    target = next((r for r in rows if r["id"] == body.get("id")), None) if body.get("id") else None
                    if target is None:
                        clash = next((r for r in rows if r["slug"] == data.get("slug")), None)
                        if clash and not body.get("overwrite"):
                            return self._json(409, {"error": f'Trên web đã có “{clash["title"]}” với đường dẫn {clash["slug"]}.'})
                        target = clash
                    if target is None:
                        missing = [k for k in REQUIRED[entity] if not data.get(k)]
                        if missing:
                            return self._json(400, {"error": "Missing: " + ", ".join(missing)})
                        target = {**data, "id": f"id{len(rows) + 1}", "status": "draft"}
                        rows.append(target)
                        return self._json(200, {"id": target["id"], "created": True, "status": "draft"})
                    target.update({k: v for k, v in data.items() if k != "status"})
                    return self._json(200, {"id": target["id"], "created": False, "status": target["status"]})
                return self._json(400, {"error": "Unknown action"})

        self.srv = ThreadingHTTPServer(("127.0.0.1", port), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


if __name__ == "__main__":
    s = FakeSite(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
    print("fake site at", s.base, "token", TOKEN)
    threading.Event().wait()
