"""Find ebooks in a folder: a PDF and a cover image that share the same file name."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").replace("đ", "d").replace("Đ", "D"))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def title_from_stem(stem: str) -> str:
    """'The-Book-of-Enoch_1-The-Watchers' -> 'The Book of Enoch 1 The Watchers'."""
    return re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", stem)).strip()


def scan_folder(folder: str) -> dict:
    """-> {"ebooks": [{id, title, pdf, cover}], "no_cover": [pdf names], "no_pdf": [image names]}"""
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise ValueError(f"Không thấy thư mục: {folder}")
    files = sorted(p for p in root.iterdir() if p.is_file() and not p.name.startswith("."))
    images = {p.stem.lower(): p for p in files if p.suffix.lower() in IMAGE_EXT}
    ebooks, no_cover, used = [], [], set()
    for pdf in (p for p in files if p.suffix.lower() == ".pdf"):
        cover = images.get(pdf.stem.lower())
        if cover:
            used.add(pdf.stem.lower())
        else:
            no_cover.append(pdf.name)
        ebooks.append({"id": str(pdf), "title": title_from_stem(pdf.stem), "pdf": str(pdf),
                       "cover": str(cover) if cover else ""})
    no_pdf = [p.name for k, p in images.items() if k not in used]
    return {"ebooks": ebooks, "no_cover": no_cover, "no_pdf": sorted(no_pdf)}
