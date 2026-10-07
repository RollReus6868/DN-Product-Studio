"""A stand-in for the website's toolApi function, with the same contract.

Used by the tests and for trying the tool without touching the real site:
    python tools/fake_site.py 8765        (token: test-token-0123456789abcdefgh)
then start the tool with DNPS_SITE_API=http://127.0.0.1:8765/functions/v1/toolApi
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
OLD_PDF = re.compile(r"^mp/private/[^/]+/[0-9a-f]+_(.+)$")


class FakeSite:
    def __init__(self, port: int = 0):
        self.records: dict[str, list[dict]] = {"Ebook": [], "Product": []}
        self.chats: list[dict] = []       # conversations, each with its "messages"
        self.orders: list[dict] = []      # what the "orders" action returns
        self.traffic: dict = {"summary": {}, "days": [], "pages": []}
        self.files: list[dict] = []       # uploaded files, in order
        self.tickets: dict[str, dict] = {}
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

            def do_PUT(self):  # noqa: N802 - the one-time upload address (the site's file storage)
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                ticket = site.tickets.pop(self.path, None)
                if ticket is None:
                    return self._json(400, {"error": "invalid upload token"})
                if site.fail_upload:
                    return self._json(413, {"error": "The object exceeded the maximum allowed size"})
                boundary = (self.headers.get("Content-Type") or "").split("boundary=")[1].encode()
                part = next(p for p in raw.split(b"--" + boundary) if b'name="file"' in p)
                data = part.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0]
                site.files.append({**ticket, "size": len(data), "head": data[:4]})
                return self._json(200, {"Key": ticket["ref"]})

            def do_POST(self):  # noqa: N802
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if not self.path.endswith("/functions/v1/toolApi"):
                    return self._json(404, {"error": "not found"})
                if self.headers.get("X-Tool-Token") != TOKEN:
                    return self._json(401, {"error": "Unauthorized"})
                body = json.loads(raw or b"{}")
                action = body.get("action")
                if action == "ping":
                    return self._json(200, {"ok": True, "site": "Dark Network (giả lập)"})
                if action == "chat_list":
                    return self._json(200, {"conversations": [{k: v for k, v in c.items() if k != "messages"} for c in site.chats]})
                if action in ("chat_thread", "chat_reply"):
                    conv = next((c for c in site.chats if c["id"] == body.get("conversation_id")), None)
                    if conv is None:
                        return self._json(400, {"error": "Missing conversation"})
                    if action == "chat_thread":
                        conv["unread_for_admin"] = False
                        return self._json(200, {"messages": conv["messages"]})
                    text = str(body.get("body") or "").strip()
                    if not text:
                        return self._json(400, {"error": "Missing conversation or message"})
                    msg = {"id": f"m{len(conv['messages']) + 1}-{conv['id']}", "sender_role": "admin", "sender_name": "Dark Network",
                           "body": text, "created_date": "2026-10-07T16:30:00Z"}
                    conv["messages"].append(msg)
                    conv.update(last_message_preview=text[:140], unread_for_admin=False)
                    return self._json(200, {"message": msg})
                if action == "orders":
                    return self._json(200, {"items": site.orders})
                if action == "traffic":
                    return self._json(200, site.traffic)
                if action == "upload_url":
                    name = str(body.get("name") or "")
                    if not re.search(r"\.(pdf|jpe?g|png|webp)$", name, re.I):
                        return self._json(400, {"error": "Only pdf, jpg, png, webp"})
                    n = len(site.tickets) + len(site.files) + 1
                    private = body.get("private") is True
                    stored = f"{n:08x}_{name}"
                    ref = stored if private else f"{site.base}/storage/v1/object/public/public-files/{stored}"
                    site.tickets[f"/upload/{n}"] = {"name": name, "private": private, "ref": ref}
                    return self._json(200, {"upload_url": f"{site.base}/upload/{n}", "ref": ref})
                ebooks = site.records["Ebook"]
                old = lambda r: (OLD_PDF.match(str(r.get("secure_file_uri") or "")) or [None, None])[1]  # noqa: E731
                if action == "pending_pdfs":
                    return self._json(200, {"items": [{"title": r["title"], "file_name": old(r)} for r in ebooks if old(r)]})
                if action == "attach_pdf":
                    hit = [r for r in ebooks if (old(r) or "").lower() == str(body.get("file_name") or "").lower()]
                    for r in hit:
                        r["secure_file_uri"] = body.get("file_uri")
                    return self._json(200, {"attached": [r["title"] for r in hit]})
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
        self.api = f"{self.base}/functions/v1/toolApi"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


if __name__ == "__main__":
    s = FakeSite(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
    print("fake site at", s.api, "token", TOKEN)
    threading.Event().wait()
