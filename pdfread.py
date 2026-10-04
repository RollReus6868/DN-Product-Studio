"""Pull the page count and the useful text out of an ebook PDF for the prompt."""
from __future__ import annotations

import logging
import re

logging.getLogger("pypdf").setLevel(logging.ERROR)   # broken files are reported to the user, not the console

HEAD_CHARS = 30000   # front matter, contents, introduction
TAIL_CHARS = 6000    # closing chapter / back matter


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def read_pdf(path: str) -> dict:
    """-> {"pages": int, "head": str, "tail": str}. Scanned PDFs give empty text."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(path)
        pages = len(reader.pages)
    except Exception as exc:  # noqa: BLE001 - pypdf raises many types on broken files
        raise ValueError(f"Không đọc được PDF ({exc.__class__.__name__}). File có thể bị hỏng hoặc có mật khẩu.") from exc

    def grab(indexes, limit):
        out, size = [], 0
        for i in indexes:
            try:
                t = _clean(reader.pages[i].extract_text() or "")
            except Exception:  # noqa: BLE001 - skip an unreadable page
                t = ""
            if t:
                out.append(t)
                size += len(t)
            if size >= limit:
                break
        return out

    head = grab(range(pages), HEAD_CHARS)
    head_text = "\n\n".join(head)[:HEAD_CHARS]
    tail_text = ""
    if pages > len(head):   # the book is longer than what the head covers
        tail = grab(range(pages - 1, len(head) - 1, -1), TAIL_CHARS)
        tail_text = "\n\n".join(reversed(tail))[-TAIL_CHARS:]
    return {"pages": pages, "head": head_text, "tail": tail_text}
