"""Make files lighter before they go to the website (Supabase's free plan counts every byte
customers download, and storage).

- Pictures: WebP, at most the size the site shows them at x2. A 3 MB PNG cover becomes ~70 KB.
- PDFs: by default only lossless changes (pages, text and pictures stay exactly the same):
  compressed page streams, duplicate objects merged, unused objects dropped. "Strong" also
  re-saves big pictures inside the PDF as JPEG (quality 80, at most 1800 px), which shrinks
  scanned or photo-heavy books a lot but changes those pictures slightly.
  The lighter copy is used only when it is really smaller and still opens with every page.
"""
from __future__ import annotations

import io

COVER_BOX = (640, 960)     # ebook covers: the site shows them at about 320 px wide
PHOTO_BOX = (1000, 1500)   # POD product photos
MIN_GAIN = 0.03            # keep the original unless the copy is at least 3 % smaller
STRONG_MAX_SIDE = 1800
STRONG_QUALITY = 80


def web_image(source, box: tuple[int, int] = PHOTO_BOX, quality: int = 80) -> bytes:
    """source: a path or bytes. -> WebP bytes no larger than box (never enlarged)."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") and _has_alpha(im) else "RGB")
        im.thumbnail(box)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=quality, method=6)
        return buf.getvalue()


def _has_alpha(im) -> bool:
    if im.mode == "P":
        return "transparency" in im.info
    return im.getextrema()[-1][0] < 255 if im.mode in ("RGBA", "LA") else False


def shrink_pdf(path: str, strong: bool = False) -> tuple[bytes | None, int, int]:
    """-> (lighter bytes or None to keep the original, original size, new size)."""
    from pypdf import PdfReader, PdfWriter

    with open(path, "rb") as f:
        original = f.read()
    before = len(original)
    try:
        reader = PdfReader(io.BytesIO(original))
        if reader.is_encrypted:
            return None, before, before
        pages = len(reader.pages)
        writer = PdfWriter(clone_from=reader)
        if strong:
            _shrink_pictures(writer)
        for page in writer.pages:
            page.compress_content_streams(level=9)
        writer.compress_identical_objects()   # merge duplicates, drop unused objects
        buf = io.BytesIO()
        writer.write(buf)
        data = buf.getvalue()
        # the copy must open and keep every page
        if len(PdfReader(io.BytesIO(data)).pages) != pages:
            return None, before, before
    except Exception:  # noqa: BLE001 - an unusual PDF is uploaded as it is
        return None, before, before
    if len(data) > before * (1 - MIN_GAIN):
        return None, before, before
    return data, before, len(data)


def _shrink_pictures(writer) -> None:
    from PIL import Image

    for page in writer.pages:
        for img in page.images:
            try:
                pic = img.image
                if pic is None or pic.mode not in ("RGB", "L") or min(pic.size) < 200:
                    continue   # masks, tiny icons and unusual colour modes stay as they are
                if max(pic.size) > STRONG_MAX_SIDE:
                    pic = pic.copy()
                    pic.thumbnail((STRONG_MAX_SIDE, STRONG_MAX_SIDE), Image.LANCZOS)
                # only when it really helps: an already well-compressed photo stays as it is
                stored = img.indirect_reference.get_object() if img.indirect_reference else None
                old = len(getattr(stored, "_data", b"") or b"")
                test = io.BytesIO()
                pic.save(test, "JPEG", quality=STRONG_QUALITY)
                if old and test.tell() > old * 0.9:
                    continue
                img.replace(pic, quality=STRONG_QUALITY)
            except Exception:  # noqa: BLE001 - keep a picture pypdf cannot re-encode
                continue


def human_size(n: int) -> str:
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{max(1, round(n / 1024))} KB"
