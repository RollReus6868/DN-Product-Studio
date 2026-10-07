"""Local web server behind the window: serves the UI and a small JSON API.

Bound to 127.0.0.1 on a random port. Every API call must carry the per-run
session key (injected into index.html), so other web pages on this computer
cannot drive the tool.
"""
from __future__ import annotations

import io
import json
import os
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pdfread
import prompts
import scan
import spring
import storage
import updater
import webstore
from app_info import APP_NAME, APP_VERSION

KEY = secrets.token_urlsafe(24)
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml",
        ".woff2": "font/woff2"}

window = None                 # the pywebview window, set by launcher
on_quit = None                # callable that closes the app (set by launcher)
_lock = threading.RLock()     # guards items.json read-modify-write
_pdf_cache: dict = {}
_thumbs: dict = {}
_update = {"state": "idle", "got": 0, "total": 0, "error": "", "release": None}


class ApiError(Exception):
    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.code = code


def ui_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "ui"


# ------------------------------------------------------------------ items
def _client(cfg: dict) -> webstore.SiteClient:
    return webstore.SiteClient(cfg["site_api_url"], storage.get_token())


def _get(kind: str, item_id: str) -> tuple[dict, dict]:
    if kind not in ("ebook", "pod"):
        raise ApiError("Loại sản phẩm không hợp lệ.")
    items = storage.load_items()
    item = items[kind].get(item_id)
    if not item:
        raise ApiError("Không thấy sản phẩm này trong danh sách. Hãy quét lại.")
    return items, item


def _public(item: dict, kind: str) -> dict:
    web = item.get("web") or {}
    out = {k: item.get(k) for k in ("id", "title", "price", "pages", "category", "spring_url", "images")
           if k in item}
    out.update(kind=kind, has_listing=bool(item.get("listing")), has_cover=bool(item.get("cover")),
               subtitle=(item.get("listing") or {}).get("subtitle") or (item.get("listing") or {}).get("seo_title", ""),
               web_status=web.get("status", "") if web.get("id") else "", slug=web.get("slug", ""))
    if kind == "ebook":
        out["file"] = Path(item["pdf"]).name
    return out


def api_state(_body: dict) -> dict:
    cfg = storage.load_config()
    items = storage.load_items()
    folder = cfg["ebook_folder"]
    ebooks = [_public(i, "ebook") for i in items["ebook"].values()
              if folder and Path(i["id"]).parent == Path(folder) and Path(i["id"]).is_file()]
    return {"app": {"name": APP_NAME, "version": APP_VERSION, "kind": updater.install_kind(),
                    "kind_text": updater.KIND_TEXT.get(updater.install_kind(), ""),
                    "native": window is not None},
            "config": cfg, "has_token": bool(storage.get_token()),
            "ebooks": ebooks, "pods": [_public(i, "pod") for i in items["pod"].values()]}


def api_config(body: dict) -> dict:
    changes = dict(body)
    if "default_price" in changes:
        try:
            changes["default_price"] = round(float(changes["default_price"]), 2)
        except (TypeError, ValueError) as exc:
            raise ApiError("Giá mặc định phải là số, ví dụ 9.99") from exc
        if not 0 < changes["default_price"] < 10000:
            raise ApiError("Giá mặc định phải lớn hơn 0.")
    if "shared_variant_id" in changes:
        changes["shared_variant_id"] = str(changes["shared_variant_id"]).strip()
        if changes["shared_variant_id"] and not changes["shared_variant_id"].isdigit():
            raise ApiError("Variant ID chỉ gồm chữ số (ví dụ 2204367).")
    storage.save_config(changes)
    return api_state({})


def api_pick_folder(_body: dict) -> dict:
    if window is None:
        raise ApiError("Hãy dán đường dẫn thư mục vào ô bên cạnh.")
    import webview

    kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
    if kind is None:
        kind = webview.FOLDER_DIALOG
    picked = window.create_file_dialog(kind)
    return {"folder": (picked[0] if picked else "")}


def api_scan(body: dict) -> dict:
    folder = str(body.get("folder") or "").strip().strip('"')
    if not folder:
        raise ApiError("Chưa chọn thư mục chứa PDF và ảnh bìa.")
    try:
        found = scan.scan_folder(folder)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    cfg = storage.save_config({"ebook_folder": str(Path(folder).expanduser())})
    with _lock:
        items = storage.load_items()
        for eb in found["ebooks"]:
            old = items["ebook"].get(eb["id"])
            if old:
                old["cover"] = eb["cover"]
            else:
                items["ebook"][eb["id"]] = {**eb, "price": cfg["default_price"]}
        storage.save_items(items)
    return {**api_state({}), "no_cover": found["no_cover"], "no_pdf": found["no_pdf"]}


def api_item_update(body: dict) -> dict:
    with _lock:
        items, item = _get(body.get("kind"), body.get("id"))
        if "title" in body:
            title = str(body["title"]).strip()
            if not title:
                raise ApiError("Tên sản phẩm không được để trống.")
            item["title"] = title
        if "price" in body:
            try:
                price = round(float(str(body["price"]).replace(",", ".")), 2)
            except ValueError as exc:
                raise ApiError("Giá phải là số, ví dụ 9.99") from exc
            if not 0 < price < 10000:
                raise ApiError("Giá phải lớn hơn 0.")
            item["price"] = price
        if "category" in body:
            if body["category"] not in spring.CATEGORIES:
                raise ApiError("Danh mục không hợp lệ.")
            item["category"] = body["category"]
        storage.save_items(items)
    return {"item": _public(item, body["kind"])}


def api_item_remove(body: dict) -> dict:
    with _lock:
        items, _item = _get(body.get("kind"), body.get("id"))
        del items[body["kind"]][body["id"]]
        storage.save_items(items)
    return {}


def api_item_prompt(body: dict) -> dict:
    kind = body.get("kind")
    items, item = _get(kind, body.get("id"))
    if kind == "pod":
        return {"prompt": prompts.pod_prompt(item), "attach": "ảnh sản phẩm (nếu muốn mô tả sát thiết kế)"}
    sig = webstore.file_sig(item["pdf"])
    pdf = _pdf_cache.get((item["pdf"], sig))
    if pdf is None:
        try:
            pdf = pdfread.read_pdf(item["pdf"])
        except ValueError as exc:
            raise ApiError(str(exc)) from exc
        _pdf_cache[(item["pdf"], sig)] = pdf
        with _lock:
            items, item = _get(kind, body["id"])
            item["pages"] = pdf["pages"]
            storage.save_items(items)
    return {"prompt": prompts.ebook_prompt(item["title"], float(item.get("price") or 0), pdf),
            "attach": "" if pdf["head"].strip() else "file PDF (tool không đọc được chữ trong PDF này)",
            "pages": pdf["pages"]}


def api_item_reply(body: dict) -> dict:
    kind = body.get("kind")
    try:
        listing = prompts.parse_reply(str(body.get("text") or ""), kind if kind in ("ebook", "pod") else "ebook")
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    with _lock:
        items, item = _get(kind, body.get("id"))
        item["listing"] = listing
        storage.save_items(items)
    return {"item": _public(item, kind), "listing": listing}


def api_item_listing(body: dict) -> dict:
    _items, item = _get(body.get("kind"), body.get("id"))
    return {"listing": item.get("listing") or None}


def api_item_publish(body: dict) -> dict:
    kind = body.get("kind")
    items, item = _get(kind, body.get("id"))
    cfg = storage.load_config()
    fn = webstore.publish_ebook if kind == "ebook" else webstore.publish_pod
    try:
        fn(item, cfg, _client(cfg), overwrite=bool(body.get("overwrite")))
    except webstore.SiteError as exc:
        raise ApiError(str(exc), exc.code) from exc
    finally:
        # uploads that succeeded are remembered even when a later step fails
        with _lock:
            fresh = storage.load_items()
            if body["id"] in fresh[kind]:
                fresh[kind][body["id"]]["web"] = item.get("web") or {}
                storage.save_items(fresh)
    return {"item": _public(item, kind)}


def api_pods_add(body: dict) -> dict:
    urls = [u.strip() for u in str(body.get("urls") or "").split() if u.strip()]
    if not urls:
        raise ApiError("Hãy dán ít nhất một link Spring.")
    added, errors = 0, []
    for url in dict.fromkeys(urls):
        try:
            info = spring.fetch(url)
            if not info["title"] or not info["images"]:
                raise ValueError("Trang này không công bố tên hoặc ảnh sản phẩm nên tool không đọc được.")
        except ValueError as exc:
            errors.append({"url": url, "error": str(exc)})
            continue
        with _lock:
            items = storage.load_items()
            old = items["pod"].get(url, {})
            items["pod"][url] = {**old, **info, "id": url, "title": old.get("title") or info["title"],
                                 "price": old.get("price") or info["price"] or 0,
                                 "category": old.get("category") or info["category"]}
            storage.save_items(items)
        added += 1
    return {**api_state({}), "added": added, "errors": errors}


# ------------------------------------------------------------------ PDFs of books copied from the old site
def _local_pdfs(cfg: dict) -> dict:
    folder = Path(cfg["ebook_folder"]) if cfg["ebook_folder"] else None
    if not folder or not folder.is_dir():
        return {}
    return {p.name.lower(): p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"}


def api_restore_list(_body: dict) -> dict:
    cfg = storage.load_config()
    try:
        pending = _client(cfg).pending_pdfs()
    except webstore.SiteError as exc:
        raise ApiError(str(exc), exc.code) from exc
    local = _local_pdfs(cfg)
    return {"items": [{**p, "found": p["file_name"].lower() in local} for p in pending]}


def api_restore_one(body: dict) -> dict:
    cfg = storage.load_config()
    path = _local_pdfs(cfg).get(str(body.get("file_name") or "").lower())
    if not path:
        raise ApiError("Không thấy file này trong thư mục đang chọn.")
    try:
        return {"attached": webstore.restore_pdf(str(path), _client(cfg))}
    except webstore.SiteError as exc:
        raise ApiError(str(exc), exc.code) from exc


# ------------------------------------------------------------------ site + token
def api_site_ping(_body: dict) -> dict:
    cfg = storage.load_config()
    try:
        return _client(cfg).ping()
    except webstore.SiteError as exc:
        raise ApiError(str(exc), exc.code) from exc


def api_orders(_body: dict) -> dict:
    try:
        return {"items": _client(storage.load_config()).orders()}
    except webstore.SiteError as exc:
        raise ApiError(str(exc), exc.code) from exc


def api_traffic(_body: dict) -> dict:
    try:
        return _client(storage.load_config()).traffic()
    except webstore.SiteError as exc:
        raise ApiError(str(exc), exc.code) from exc


def api_token_generate(_body: dict) -> dict:
    token = secrets.token_urlsafe(36)
    return api_token_set({"token": token})


def api_token_set(body: dict) -> dict:
    token = str(body.get("token") or "").strip()
    if len(token) < 24:
        raise ApiError("Mã bí mật phải dài ít nhất 24 ký tự.")
    try:
        storage.set_token(token)
    except Exception as exc:  # noqa: BLE001 - keyring backends raise their own types
        raise ApiError(f"Không lưu được mã vào kho mật khẩu của máy ({exc.__class__.__name__}).") from exc
    return {"token": token}


def api_token_show(_body: dict) -> dict:
    return {"token": storage.get_token()}


def api_open(body: dict) -> dict:
    url = str(body.get("url") or "")
    if not url.startswith(("https://", "http://")):
        raise ApiError("Link không hợp lệ.")
    webbrowser.open(url)
    return {}


# ------------------------------------------------------------------ update
def api_update_check(_body: dict) -> dict:
    try:
        rel = updater.fetch_latest()
    except updater.UpdateError as exc:
        raise ApiError(str(exc)) from exc
    _update["release"] = rel
    kind = updater.install_kind()
    return {"current": APP_VERSION, "latest": rel.version, "newer": updater.is_newer(rel.version),
            "notes": rel.notes, "url": rel.html_url,
            "auto": kind in ("win-setup", "win-portable", "mac-app") and bool(updater.pick_asset(rel, kind))}


def _install_worker(rel, kind: str) -> None:
    try:
        dest = storage.app_dir() / "updates"
        asset = updater.pick_asset(rel, kind)
        path = updater.download_asset(rel, asset, dest, progress=lambda g, t: _update.update(got=g, total=t))
        new, staging = path, ""
        if kind == "mac-app":
            staging = str(dest / f"mac_{rel.version}")
            new = str(updater.extract_mac_zip(path, staging))
        updater.launch_helper(kind, new_path=new, target=updater.current_target(kind),
                              log=str(dest / "update_log.txt"), staging=staging)
        _update["state"] = "restarting"
        if on_quit:
            threading.Timer(1.0, on_quit).start()
    except Exception as exc:  # noqa: BLE001 - shown to the user
        _update.update(state="error", error=str(exc) or exc.__class__.__name__)


def api_update_install(_body: dict) -> dict:
    rel = _update.get("release")
    kind = updater.install_kind()
    if not rel or not updater.is_newer(rel.version):
        raise ApiError("Chưa có bản mới. Bấm “Kiểm tra cập nhật” trước.")
    if kind not in ("win-setup", "win-portable", "mac-app") or not updater.pick_asset(rel, kind):
        raise ApiError("Kiểu cài đặt này không tự cập nhật được. Hãy tải bản mới ở trang Releases.")
    if _update["state"] == "downloading":
        return {}
    _update.update(state="downloading", got=0, total=0, error="")
    threading.Thread(target=_install_worker, args=(rel, kind), daemon=True).start()
    return {}


def api_update_progress(_body: dict) -> dict:
    return {k: _update[k] for k in ("state", "got", "total", "error")}


ROUTES = {
    "/api/state": api_state, "/api/config": api_config, "/api/pick-folder": api_pick_folder,
    "/api/ebooks/scan": api_scan, "/api/pods/add": api_pods_add,
    "/api/item/update": api_item_update, "/api/item/remove": api_item_remove,
    "/api/item/prompt": api_item_prompt, "/api/item/reply": api_item_reply,
    "/api/item/listing": api_item_listing, "/api/item/publish": api_item_publish,
    "/api/restore/list": api_restore_list, "/api/restore/one": api_restore_one,
    "/api/site/ping": api_site_ping, "/api/orders": api_orders, "/api/traffic": api_traffic, "/api/token/generate": api_token_generate,
    "/api/token/set": api_token_set, "/api/token/show": api_token_show, "/api/open": api_open,
    "/api/update/check": api_update_check, "/api/update/install": api_update_install,
    "/api/update/progress": api_update_progress,
}


# ------------------------------------------------------------------ http
def _thumb(path: str) -> bytes:
    sig = (path, webstore.file_sig(path))
    if sig not in _thumbs:
        from PIL import Image

        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((240, 336))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
        _thumbs[sig] = buf.getvalue()
    return _thumbs[sig]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):   # keep the console quiet
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _local(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        if not self._local():
            return self._send(403, b"forbidden", "text/plain")
        if url.path == "/api/cover":
            q = parse_qs(url.query)
            if q.get("k", [""])[0] != KEY:
                return self._send(403, b"forbidden", "text/plain")
            item = storage.load_items()["ebook"].get(q.get("id", [""])[0])
            try:
                return self._send(200, _thumb(item["cover"]), "image/jpeg")
            except Exception:  # noqa: BLE001 - missing / unreadable cover: the UI shows a placeholder
                return self._send(404, b"", "text/plain")
        name = "index.html" if url.path in ("/", "/index.html") else url.path.lstrip("/")
        file = (ui_dir() / name).resolve()
        if ui_dir().resolve() not in file.parents or not file.is_file():
            return self._send(404, b"not found", "text/plain")
        body = file.read_bytes()
        if name == "index.html":
            body = body.replace(b"__SESSION_KEY__", KEY.encode())
        self._send(200, body, MIME.get(file.suffix, "application/octet-stream"))

    def do_POST(self):  # noqa: N802
        fn = ROUTES.get(urlparse(self.path).path)
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))   # always drain: keep-alive
        if not self._local() or self.headers.get("X-Session") != KEY:
            return self._json(403, {"error": "Phiên làm việc không hợp lệ. Hãy mở lại tool."})
        if fn is None:
            return self._json(404, {"error": "not found"})
        try:
            body = json.loads(raw or b"{}")
            self._json(200, fn(body if isinstance(body, dict) else {}))
        except ApiError as exc:
            self._json(400, {"error": str(exc), "code": exc.code})
        except Exception as exc:  # noqa: BLE001 - never kill the request thread silently
            self._json(500, {"error": f"Lỗi trong tool: {exc.__class__.__name__}: {exc}"})


def start(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", port or int(os.environ.get("DNPS_PORT") or 0)), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"
