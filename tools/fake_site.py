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

# print on demand: what the site answers for pod_catalog / pod_blueprint (the real numbers come from Printify)
POD_BLUEPRINTS = {
    12: {"title": "Unisex Jersey Short Sleeve Tee", "brand": "Bella+Canvas", "model": "3001", "category": "tshirts",
         "provider": {"id": 99, "title": "Printify Choice"}, "from_cost": 1129, "default_price": 2199, "embroidery": False,
         "colors": [{"id": 521, "title": "White", "hex": "#ffffff"}, {"id": 418, "title": "Black", "hex": "#000000"},
                    {"id": 511, "title": "Navy", "hex": "#1f2a44"}],
         "sizes": [{"id": 14, "title": "S"}, {"id": 15, "title": "M"}, {"id": 16, "title": "L"}, {"id": 17, "title": "XL"}, {"id": 18, "title": "2XL"}],
         "positions": [{"position": "front", "width": 3600, "height": 4200, "method": "dtg"}, {"position": "back", "width": 3600, "height": 4200, "method": "dtg"}],
         "description": "<p>100% Airlume combed and ring-spun cotton. Retail fit.</p>"},
    77: {"title": "Unisex Heavy Blend™ Hooded Sweatshirt", "brand": "Gildan", "model": "18500", "category": "hoodies",
         "provider": {"id": 99, "title": "Printify Choice"}, "from_cost": 2158, "default_price": 3199, "embroidery": False,
         "colors": [{"id": 418, "title": "Black", "hex": "#000000"}], "sizes": [{"id": 14, "title": "S"}, {"id": 15, "title": "M"}],
         "positions": [{"position": "front", "width": 3200, "height": 2100, "method": "dtg"}], "description": "<p>50% cotton, 50% polyester.</p>"},
    1687: {"title": "Unisex Nantucket Crewneck Sweatshirt (Embroidery)", "brand": "Lane Seven", "model": "LS11004", "category": "embroidery",
           "provider": {"id": 99, "title": "Printify Choice"}, "from_cost": 2737, "default_price": 3799, "embroidery": True,
           "colors": [{"id": 5453, "title": "Navy Blue", "hex": "#4d6589"}], "sizes": [{"id": 14, "title": "S"}],
           "positions": [{"position": "front_left_chest", "width": 1200, "height": 1200, "method": "embroidery"}], "description": "<p>Embroidered.</p>"},
}
for _id, _bp in POD_BLUEPRINTS.items():
    _bp["id"] = _id
    _bp["variants"] = [[_id * 1000 + i * 10 + j, c["id"], z["id"], _bp["from_cost"] + (219 if z["title"] == "2XL" else 0), 1]
                       for i, c in enumerate(_bp["colors"]) for j, z in enumerate(_bp["sizes"])]
    _bp["max_variants"] = 100
POD_NAMES = {"tshirts": "T-shirts", "hoodies": "Hoodies", "sweatshirts": "Sweatshirts", "embroidery": "Embroidery"}


class FakeSite:
    def __init__(self, port: int = 0):
        self.records: dict[str, list[dict]] = {"Ebook": [], "Product": []}
        self.chats: list[dict] = []       # conversations, each with its "messages"
        self.orders: list[dict] = []      # what the "orders" action returns
        self.analytics: dict = {}            # what the "analytics" action returns
        self.analytics_days: list[int] = []  # the ranges the tool asked for
        self.files: list[dict] = []       # uploaded files, in order
        self.tickets: dict[str, dict] = {}
        self.blobs: dict[str, bytes] = {}  # public files by their address path (served back by GET)
        self.fail_upload = False
        self.pod_created: list[dict] = []      # what pod_create received
        self.pod_probed: list[int] = []        # blueprint ids whose prices were read
        self.pod_synced = 0
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
                if not ticket["private"]:
                    site.blobs[ticket["ref"][len(site.base):]] = data
                site.files.append({**ticket, "size": len(data), "head": data[:4],
                                   "cache_field": b'name="cacheControl"\r\n\r\n31536000' in raw})
                return self._json(200, {"Key": ticket["ref"]})

            def do_GET(self):  # noqa: N802 - public pictures, as the site's storage serves them
                data = site.blobs.get(self.path)
                if data is None:
                    return self._json(404, {"error": "not found"})
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

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
                if action == "analytics":
                    site.analytics_days.append(body.get("days"))
                    return self._json(200, {**site.analytics, "days_range": body.get("days")})
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
                if action == "media_list":
                    return self._json(200, {"items": [
                        *[{"entity": "Ebook", "id": r["id"], "title": r["title"], "images": [r["cover_image"]]}
                          for r in ebooks if r.get("cover_image")],
                        *[{"entity": "Product", "id": r["id"], "title": r["title"], "images": r["images"]}
                          for r in site.records["Product"] if r.get("images")]]})
                if action == "set_media":
                    own = f"{site.base}/storage/v1/object/public/public-files/"
                    images = body.get("images") if isinstance(body.get("images"), list) else []
                    if body.get("entity") not in site.records or not images or not all(str(u).startswith(own) for u in images):
                        return self._json(400, {"error": "Bad images"})
                    row = next((r for r in site.records[body["entity"]] if r["id"] == body.get("id")), None)
                    if row is None:
                        return self._json(404, {"error": "Not found"})
                    current = [row["cover_image"]] if body["entity"] == "Ebook" else row["images"]
                    if len(current) != len(images):
                        return self._json(409, {"error": "Picture count changed"})
                    row.update({"cover_image": images[0]} if body["entity"] == "Ebook" else {"images": images})
                    return self._json(200, {"ok": True})
                entity = body.get("entity")
                if entity not in site.records and not str(action).startswith("pod_"):
                    return self._json(400, {"error": "Unknown entity"})
                rows = site.records.get(entity, [])
                if str(action).startswith("pod_"):
                    if action == "pod_catalog":
                        cats = []
                        for key, name in POD_NAMES.items():
                            items = [{"id": i, "title": b["title"], "brand": b["brand"], "model": b["model"], "image": "",
                                      "from_cost": b["from_cost"] if i in site.pod_probed else None,
                                      "provider": b["provider"]["title"] if i in site.pod_probed else None}
                                     for i, b in POD_BLUEPRINTS.items() if b["category"] == key]
                            items += [{"id": 9000 + n, "title": f"Other {name} {n}", "brand": "Generic", "model": "", "image": "",
                                       "from_cost": None, "provider": None} for n in range(3)]
                            cats.append({"key": key, "name": name, "bestsellers": items[:5], "all": items})
                        return self._json(200, {"categories": cats})
                    if action == "pod_blueprint":
                        bp = POD_BLUEPRINTS.get(int(body.get("blueprint_id") or 0))
                        if not bp:
                            return self._json(500, {"error": "Printify 404: blueprint not found"})
                        site.pod_probed.append(bp["id"])
                        return self._json(200, bp)
                    if action == "pod_sync":
                        site.pod_synced += 1
                        return self._json(200, {"created": ["Made In Printify Tee"], "updated": [], "skipped": [], "missing": []})
                    if action == "pod_create":
                        own = f"{site.base}/storage/v1/object/public/public-files/"
                        url = str(body.get("design_url") or "")
                        bp = POD_BLUEPRINTS.get(int(body.get("blueprint_id") or 0))
                        listing = body.get("listing") or {}
                        if not url.startswith(own) or url[len(site.base):] not in site.blobs:
                            return self._json(400, {"error": "Ảnh thiết kế phải là PNG/JPG đã tải lên web."})
                        if not bp or not body.get("colors") or not body.get("sizes") or not listing.get("title") or not listing.get("description"):
                            return self._json(400, {"error": "Thiếu loại, màu, size hoặc mô tả."})
                        site.pod_created.append(body)
                        site.blobs.pop(url[len(site.base):], None)   # the site drops its copy once Printify has it
                        price = float(body.get("price") or 0) or bp["default_price"] / 100
                        rid = f"pod{len(site.pod_created)}"
                        site.records["Product"].append({"id": rid, "title": listing["title"], "status": "draft", "printify": True})
                        return self._json(200, {"id": rid, "created": True, "printify_product_id": f"pf{len(site.pod_created)}",
                                                "price": price, "variants": len(body["colors"]) * len(body["sizes"]), "mockups": 12})
                    return self._json(400, {"error": "Unknown action"})
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
