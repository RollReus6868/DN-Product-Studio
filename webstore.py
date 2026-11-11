"""Talk to the website (its `toolApi` backend function) and publish drafts.

The site checks a secret token on every call, creates new records as drafts,
and stores ebook PDFs as private files. Orders and visits are read-only; the customer chat can be read and answered. Nothing here can
publish or delete.
"""
from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path

import requests

import shrink
from app_info import APP_ID, APP_VERSION
from scan import slugify

SHIPPING_INFO = "<p>Printed and shipped by Spring.</p>"


class SiteError(RuntimeError):
    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.code = code


class SiteClient:
    def __init__(self, url: str, token: str):
        self.url = url
        self.headers = {"X-Tool-Token": token, "User-Agent": f"{APP_ID}/{APP_VERSION}"}
        self.token = token

    def _call(self, timeout: float, **kw) -> dict:
        if not self.token:
            raise SiteError("Chưa có mã bí mật. Vào Cài đặt để tạo mã và dán vào Supabase.", "no_token")
        try:
            r = requests.post(self.url, headers=self.headers, timeout=timeout, **kw)
        except requests.RequestException as exc:
            raise SiteError(f"Không kết nối được website ({exc.__class__.__name__}). Kiểm tra Internet.", "network") from exc
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code == 401:
            raise SiteError("Website từ chối mã bí mật. Mã trong tool phải giống hệt secret TOOL_API_TOKEN trên Supabase.", "auth")
        if r.status_code == 404:
            raise SiteError("Không thấy cổng nhận sản phẩm (toolApi) của website. Hãy cập nhật tool lên bản mới nhất.",
                            "not_deployed")
        if r.status_code == 409:
            raise SiteError(data.get("error") or "Trên web đã có sản phẩm cùng đường dẫn.", "exists")
        if r.status_code == 413:
            raise SiteError("File quá lớn, website không nhận. Hãy tải file này lên bằng trang Admin của web.", "too_large")
        if r.status_code == 500 and "TOOL_API_TOKEN" in str(data.get("error") if isinstance(data, dict) else ""):
            raise SiteError("Website chưa có mã bí mật. Vào Supabase › Edge Functions › Secrets, thêm TOOL_API_TOKEN "
                            "bằng mã trong Cài đặt của tool.", "auth")
        if r.status_code >= 400 or not isinstance(data, dict):
            detail = (data.get("error") if isinstance(data, dict) else "") or r.text[:200]
            raise SiteError(f"Website trả lỗi HTTP {r.status_code}: {detail}", "http")
        return data

    def ping(self) -> dict:
        return self._call(30, json={"action": "ping"})

    def list(self, entity: str) -> list[dict]:
        return self._call(60, json={"action": "list", "entity": entity}).get("items") or []

    def upsert(self, entity: str, data: dict, record_id: str = "", overwrite: bool = False) -> dict:
        return self._call(60, json={"action": "upsert", "entity": entity, "data": data, "id": record_id,
                                    "overwrite": overwrite})

    def upload(self, name: str, content, private: bool) -> str:
        """content: bytes or an open binary file. Returns the public URL, or the private file URI.
        The site hands out a one-time address and the file goes straight into its storage."""
        ticket = self._call(60, json={"action": "upload_url", "name": name, "private": private})
        if not ticket.get("upload_url") or not ticket.get("ref"):
            raise SiteError("Website không cấp được địa chỉ tải file.", "http")
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        try:
            # file names are unique, so browsers may keep them for a year (saves the site's bandwidth)
            r = requests.put(ticket["upload_url"], data={"cacheControl": "31536000"},
                             files={"file": (name, content, mime)}, timeout=900)
        except requests.RequestException as exc:
            raise SiteError(f"Mất kết nối khi tải file lên ({exc.__class__.__name__}).", "network") from exc
        if r.status_code == 413 or "exceeded the maximum" in r.text:
            raise SiteError("File quá lớn (kho của website nhận tối đa 50 MB mỗi file).", "too_large")
        if r.status_code >= 400:
            raise SiteError(f"Kho file của website từ chối file (HTTP {r.status_code}): {r.text[:200]}", "http")
        return ticket["ref"]

    def orders(self) -> list[dict]:
        """One row per order, newest first: order_id, date, email, status, total (cents), currency, buyer, items."""
        return self._call(60, json={"action": "orders"}).get("items") or []

    def analytics(self, days: int) -> dict:
        """The site's own statistics for the last 7 / 28 / 90 days: visits (like Google Analytics),
        cart and checkouts, email sign-ups. See tool_analytics in the website's migrations."""
        return self._call(60, json={"action": "analytics", "days": days})

    # ---- customer chat (the same inbox as the website's Admin > Tin nhắn)
    def chat_list(self) -> list[dict]:
        return self._call(30, json={"action": "chat_list"}).get("conversations") or []

    def chat_thread(self, conversation_id: str) -> list[dict]:
        """The messages of one conversation; reading marks the customer's messages as read."""
        return self._call(30, json={"action": "chat_thread", "conversation_id": conversation_id}).get("messages") or []

    def chat_reply(self, conversation_id: str, body: str) -> dict:
        return self._call(30, json={"action": "chat_reply", "conversation_id": conversation_id, "body": body}).get("message") or {}

    # ---- pictures already on the site (to replace heavy ones with lighter copies)
    def media_list(self) -> list[dict]:
        """[{entity: "Ebook" | "Product", id, title, images: [url, ...]}]"""
        return self._call(60, json={"action": "media_list"}).get("items") or []

    def set_media(self, entity: str, record_id: str, images: list[str]) -> None:
        self._call(60, json={"action": "set_media", "entity": entity, "id": record_id, "images": images})

    def is_own_picture(self, url: str) -> bool:
        """A picture in this site's own storage (not the site's built-in /img files or another site)."""
        base = self.url.split("/functions/")[0]
        return isinstance(url, str) and url.startswith(base + "/storage/v1/object/public/public-files/")

    def pending_pdfs(self) -> list[dict]:
        """Books on the site whose PDF still has to be uploaded again: [{title, file_name}]."""
        return self._call(60, json={"action": "pending_pdfs"}).get("items") or []

    def attach_pdf(self, file_name: str, file_uri: str) -> list[str]:
        return self._call(60, json={"action": "attach_pdf", "file_name": file_name, "file_uri": file_uri}).get("attached") or []


# ------------------------------------------------------------------ files
def file_sig(path: str) -> str:
    st = os.stat(path)
    return f"{st.st_size}-{st.st_mtime_ns}"


COVER_BOX, PHOTO_BOX = shrink.COVER_BOX, shrink.PHOTO_BOX


def cover_webp(source, box: tuple[int, int] = PHOTO_BOX) -> bytes:
    """Web-ready picture (WebP, no larger than box). Book covers use COVER_BOX: a 3 MB PNG
    becomes ~60-100 KB, twice the size the site shows them at, so it stays sharp on phones."""
    return shrink.web_image(source, box, 80 if box == COVER_BOX else 82)


def _safe_name(stem: str, ext: str) -> str:
    return (slugify(stem) or "file") + ext


def pdf_for_upload(path: str, cfg: dict | None) -> tuple[object, dict]:
    """-> (bytes or an open file, {"before", "after"}). The lighter copy only when the setting is on
    and it is really smaller; otherwise the file exactly as it is."""
    mode = (cfg or {}).get("pdf_shrink", "safe")     # "off" | "safe" (lossless) | "strong"
    if mode in ("safe", "strong"):
        data, before, after = shrink.shrink_pdf(path, strong=mode == "strong")
        if data is not None:
            return data, {"before": before, "after": after}
    size = os.path.getsize(path)
    return open(path, "rb"), {"before": size, "after": size}  # noqa: SIM115 - closed by _upload_pdf


def _upload_pdf(path: str, cfg: dict | None, client: SiteClient) -> tuple[str, dict]:
    content, sizes = pdf_for_upload(path, cfg)
    try:
        return client.upload(Path(path).name, content, True), sizes   # buyers download it under its own name
    finally:
        if hasattr(content, "close"):
            content.close()


def restore_pdf(path: str, client: SiteClient, cfg: dict | None = None) -> list[str]:
    """Upload one PDF and attach it to the book(s) on the site that are waiting for that file name."""
    uri, _sizes = _upload_pdf(path, cfg, client)
    return client.attach_pdf(Path(path).name, uri)


def _is_light(url: str) -> bool:
    return url.split("?")[0].lower().endswith(".webp")


def lighten_site_pictures(client: SiteClient, progress=None) -> dict:
    """Replace the heavy pictures already on the site (JPG/PNG covers and product photos in its own
    storage) with WebP copies. The record keeps everything else; the old file stays in storage.
    -> {"done", "skipped", "failed": [titles], "before", "after"}"""
    items = client.media_list()
    todo = [i for i in items if any(client.is_own_picture(u) and not _is_light(u) for u in i["images"])]
    out = {"done": 0, "skipped": len(items) - len(todo), "failed": [], "before": 0, "after": 0}
    for n, item in enumerate(todo, 1):
        if progress:
            progress(n, len(todo), item.get("title") or "")
        box = COVER_BOX if item["entity"] == "Ebook" else PHOTO_BOX
        try:
            new, before, after = [], 0, 0
            for url in item["images"]:
                if not client.is_own_picture(url) or _is_light(url):
                    new.append(url)
                    continue
                r = requests.get(url, timeout=60)
                r.raise_for_status()
                webp = cover_webp(r.content, box)
                if len(webp) >= len(r.content):      # already small: keep it
                    new.append(url)
                    continue
                stem = re.sub(r"^[0-9a-f]{8,9}_", "", Path(url.split("?")[0]).stem)
                new.append(client.upload(_safe_name(stem, ".webp"), webp, False))
                before, after = before + len(r.content), after + len(webp)
            if new != item["images"]:
                client.set_media(item["entity"], item["id"], new)
                out["done"] += 1
                out["before"] += before
                out["after"] += after
            else:
                out["skipped"] += 1
        except (requests.RequestException, SiteError, OSError, ValueError) as exc:
            out["failed"].append(f"{item.get('title') or item['id']} ({exc.__class__.__name__})")
        except Exception as exc:  # noqa: BLE001 - Pillow raises many types on a broken picture
            out["failed"].append(f"{item.get('title') or item['id']} ({exc.__class__.__name__})")
    return out


# ------------------------------------------------------------------ publishing
def publish_ebook(item: dict, cfg: dict, client: SiteClient, overwrite: bool = False) -> dict:
    """Uploads what changed, then creates/updates the draft. Mutates and returns item["web"]."""
    listing = item.get("listing")
    if not listing:
        raise SiteError("Chưa có mô tả. Bấm “Viết mô tả” trước.", "incomplete")
    if not item.get("cover"):
        raise SiteError("Thiếu ảnh bìa cùng tên với file PDF.", "incomplete")
    for key in ("pdf", "cover"):
        if not Path(item[key]).is_file():
            raise SiteError(f"Không còn thấy file: {item[key]}", "incomplete")
    web = item.setdefault("web", {})
    slug = web.get("slug") or slugify(item["title"])
    if not slug:
        raise SiteError("Tên sản phẩm không tạo được đường dẫn. Hãy sửa tên.", "incomplete")

    sig = file_sig(item["cover"])
    if web.get("cover_sig") != sig:
        web["cover_url"] = client.upload(_safe_name(Path(item["cover"]).stem, ".webp"), cover_webp(item["cover"], COVER_BOX), False)
        web["cover_sig"] = sig
    sig = file_sig(item["pdf"])
    if web.get("pdf_sig") != sig:
        web["file_uri"], web["pdf_sizes"] = _upload_pdf(item["pdf"], cfg, client)
        web["pdf_sig"] = sig

    data = {"title": item["title"], "slug": slug, "price": float(item.get("price") or 0),
            "cover_image": web["cover_url"], "secure_file_uri": web["file_uri"], **listing}
    res = client.upsert("Ebook", data, web.get("id", ""), overwrite)
    web.update(id=res.get("id", ""), status=res.get("status", "draft"), slug=slug)
    return web


def publish_pod(item: dict, cfg: dict, client: SiteClient, overwrite: bool = False) -> dict:
    listing = item.get("listing")
    if not listing:
        raise SiteError("Chưa có mô tả. Bấm “Viết mô tả” trước.", "incomplete")
    if not item.get("images"):
        raise SiteError("Chưa có ảnh sản phẩm.", "incomplete")
    if not float(item.get("price") or 0):
        raise SiteError("Chưa có giá.", "incomplete")
    web = item.setdefault("web", {})
    slug = web.get("slug") or slugify(item["title"])
    if not slug:
        raise SiteError("Tên sản phẩm không tạo được đường dẫn. Hãy sửa tên.", "incomplete")

    if web.get("images_src") != item["images"]:
        urls = []
        for i, src in enumerate(item["images"], 1):
            try:
                r = requests.get(src, timeout=60)
                r.raise_for_status()
            except requests.RequestException as exc:
                raise SiteError(f"Không tải được ảnh {i} từ Spring ({exc.__class__.__name__}).", "network") from exc
            try:
                picture = cover_webp(r.content, PHOTO_BOX)
            except Exception as exc:  # noqa: BLE001 - Pillow raises many types on a non-image
                raise SiteError(f"Ảnh {i} từ Spring không đọc được.", "incomplete") from exc
            urls.append(client.upload(f"{slug}-{i}.webp", picture, False))
        web["image_urls"], web["images_src"] = urls, list(item["images"])

    data = {"title": item["title"], "slug": slug, "price": float(item["price"]),
            "category": item.get("category") or "Gifts", "images": web["image_urls"],
            "spring_url": item["spring_url"], "shipping_info": SHIPPING_INFO, **listing}
    res = client.upsert("Product", data, web.get("id", ""), overwrite)
    web.update(id=res.get("id", ""), status=res.get("status", "draft"), slug=slug)
    return web
