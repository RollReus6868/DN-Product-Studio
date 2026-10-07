"""Talk to the website (its `toolApi` backend function) and publish drafts.

The site checks a secret token on every call, creates new records as drafts,
and stores ebook PDFs as private files. Orders and visits are read-only. Nothing here can
publish or delete.
"""
from __future__ import annotations

import io
import mimetypes
import os
import tempfile
from pathlib import Path

import requests

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
            r = requests.put(ticket["upload_url"], files={"file": (name, content, mime)}, timeout=900)
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

    def traffic(self) -> dict:
        """The site's own visit counter: {summary, days, pages}."""
        return self._call(60, json={"action": "traffic"})

    def pending_pdfs(self) -> list[dict]:
        """Books on the site whose PDF still has to be uploaded again: [{title, file_name}]."""
        return self._call(60, json={"action": "pending_pdfs"}).get("items") or []

    def attach_pdf(self, file_name: str, file_uri: str) -> list[str]:
        return self._call(60, json={"action": "attach_pdf", "file_name": file_name, "file_uri": file_uri}).get("attached") or []


# ------------------------------------------------------------------ files
def file_sig(path: str) -> str:
    st = os.stat(path)
    return f"{st.st_size}-{st.st_mtime_ns}"


def cover_jpeg(path: str) -> bytes:
    """Web-ready cover: RGB JPEG, at most 1000x1500 (a 3 MB PNG becomes ~350 KB)."""
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((1000, 1500))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=86, progressive=True, optimize=True)
        return buf.getvalue()


def _safe_name(stem: str, ext: str) -> str:
    return (slugify(stem) or "file") + ext


def restore_pdf(path: str, client: SiteClient) -> list[str]:
    """Upload one PDF and attach it to the book(s) on the site that are waiting for that file name."""
    name = Path(path).name
    with open(path, "rb") as f:
        uri = client.upload(name, f, True)   # buyers download it under this, its own name
    return client.attach_pdf(name, uri)


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
        web["cover_url"] = client.upload(_safe_name(Path(item["cover"]).stem, ".jpg"), cover_jpeg(item["cover"]), False)
        web["cover_sig"] = sig
    sig = file_sig(item["pdf"])
    if web.get("pdf_sig") != sig:
        with open(item["pdf"], "rb") as f:
            web["file_uri"] = client.upload(Path(item["pdf"]).name, f, True)   # keeps its own name
        web["pdf_sig"] = sig

    data = {"title": item["title"], "slug": slug, "price": float(item.get("price") or 0),
            "cover_image": web["cover_url"], "secure_file_uri": web["file_uri"], **listing}
    if cfg.get("shared_variant_id"):
        data["lemon_squeezy_variant_id"] = str(cfg["shared_variant_id"]).strip()
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
            with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp:
                tmp.write(r.content)
            try:
                jpeg = cover_jpeg(tmp.name)
            except Exception as exc:  # noqa: BLE001 - Pillow raises many types on a non-image
                raise SiteError(f"Ảnh {i} từ Spring không đọc được.", "incomplete") from exc
            finally:
                os.unlink(tmp.name)
            urls.append(client.upload(f"{slug}-{i}.jpg", jpeg, False))
        web["image_urls"], web["images_src"] = urls, list(item["images"])

    data = {"title": item["title"], "slug": slug, "price": float(item["price"]),
            "category": item.get("category") or "Gifts", "images": web["image_urls"],
            "spring_url": item["spring_url"], "shipping_info": SHIPPING_INFO, **listing}
    res = client.upsert("Product", data, web.get("id", ""), overwrite)
    web.update(id=res.get("id", ""), status=res.get("status", "draft"), slug=slug)
    return web
