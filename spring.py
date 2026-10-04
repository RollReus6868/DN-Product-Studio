"""Read a product's public details from its Spring page (title, price, photos).

Works from what every storefront page publishes for search engines and social
previews: JSON-LD "Product" data and Open Graph meta tags. Nothing is logged in.
"""
from __future__ import annotations

import html as htmllib
import json
import re

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
CATEGORIES = ("Apparel", "Wall Art", "Mugs", "Gifts", "Books")
_CATEGORY_WORDS = {
    "Mugs": ("mug", "cup", "tumbler"),
    "Wall Art": ("poster", "print", "canvas", "wall art", "tapestry", "framed"),
    "Apparel": ("shirt", "tee", "hoodie", "sweatshirt", "tank", "jacket", "hat", "cap", "beanie", "legging",
                "sock", "long sleeve", "crewneck"),
    "Books": ("book", "journal", "notebook"),
}


def guess_category(title: str) -> str:
    low = title.lower()
    for cat, words in _CATEGORY_WORDS.items():
        if any(re.search(rf"\b{re.escape(w)}s?\b", low) for w in words):
            return cat
    return "Gifts"


def _meta(page: str, name: str) -> str:
    for pat in (rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]*content=["\']([^"\']*)["\']',
                rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']{re.escape(name)}["\']'):
        m = re.search(pat, page, flags=re.I)
        if m:
            return htmllib.unescape(m.group(1)).strip()
    return ""


def _json_ld_products(page: str) -> list[dict]:
    found = []
    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, flags=re.S | re.I):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                types = node.get("@type")
                if "Product" in (types if isinstance(types, list) else [types]):
                    found.append(node)
                stack.extend(v for v in node.values() if isinstance(v, (list, dict)))
    return found


def _price(value) -> float:
    m = re.search(r"\d+(?:[.,]\d+)?", str(value or "").replace(",", "."))
    return float(m.group(0)) if m else 0.0


def parse_page(page: str, url: str) -> dict:
    """-> {title, price, images, source_text, category}; empty values when the page does not publish them."""
    title, price, images, text = "", 0.0, [], ""
    for prod in _json_ld_products(page):
        title = title or str(prod.get("name") or "").strip()
        text = text or str(prod.get("description") or "").strip()
        img = prod.get("image")
        for one in (img if isinstance(img, list) else [img]):
            src = one.get("url") if isinstance(one, dict) else one
            if isinstance(src, str) and src.startswith("http") and src not in images:
                images.append(src)
        offers = prod.get("offers")
        for offer in (offers if isinstance(offers, list) else [offers]):
            if isinstance(offer, dict) and not price:
                price = _price(offer.get("price") or offer.get("lowPrice"))
    title = title or _meta(page, "og:title") or _meta(page, "twitter:title")
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.S | re.I)
        title = htmllib.unescape(m.group(1)).strip() if m else ""
    text = text or _meta(page, "og:description") or _meta(page, "description")
    price = price or _price(_meta(page, "product:price:amount") or _meta(page, "og:price:amount"))
    og = _meta(page, "og:image")
    if og.startswith("http") and og not in images:
        images.append(og)
    title = re.sub(r"\s*[|–—-]\s*(Spring|Teespring)\s*$", "", title, flags=re.I).strip()
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()[:1500]
    return {"title": title, "price": price, "images": images[:6], "source_text": text,
            "category": guess_category(title), "spring_url": url}


def fetch(url: str, timeout: float = 25) -> dict:
    url = url.strip()
    if not re.match(r"^https?://", url, flags=re.I):
        raise ValueError("Link phải bắt đầu bằng https://")
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    except requests.RequestException as exc:
        raise ValueError(f"Không mở được link ({exc.__class__.__name__}). Kiểm tra Internet.") from exc
    if r.status_code >= 400:
        raise ValueError(f"Spring trả lỗi HTTP {r.status_code} cho link này.")
    return parse_page(r.text, url)
