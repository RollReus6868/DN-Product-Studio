"""Build the prompt the user pastes into Claude / ChatGPT, and read the answer back.

No API is called from the tool: the user copies the prompt, pastes the model's
JSON answer back, and parse_reply() checks it before anything reaches the site.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

EBOOK_KEYS = {"subtitle": str, "description": str, "what_you_learn": list, "who_for": str, "faq": list,
              "seo_title": str, "meta_description": str}
POD_KEYS = {"description": str, "bible_inspiration": str, "story_behind_design": str, "product_info": str,
            "seo_title": str, "meta_description": str}
DESIGN_KEYS = {"title": str, **POD_KEYS}
REQUIRED = {"ebook": ("description", "what_you_learn", "seo_title", "meta_description"),
            "pod": ("description", "seo_title", "meta_description"),
            "design": ("title", "description", "seo_title", "meta_description")}

_RULES = """Rules:
- Write in English, for the Dark Network store (Bible-discovery books and gifts for thoughtful readers).
- Use ONLY facts from the material below. Do not invent reviews, ratings, sales numbers, endorsements, awards or author credentials.
- Do not overclaim. If the material states a limit about itself (for example "not a new translation"), keep that limit in the description.
- HTML fields may use only <p>, <h3>, <ul>, <li>, <strong>, <em>. No inline styles, no links, no images.
- meta_description: at most 160 characters. seo_title: at most 60 characters.
- Answer with ONE JSON object and nothing else: no commentary, no markdown fence."""


def ebook_prompt(title: str, price: float, pdf: dict) -> str:
    schema = {
        "subtitle": "one line, under 90 characters",
        "description": "HTML: opening hook, what the book is, what is inside (real part/chapter counts, appendices, "
                       "tools), an honest note about the edition, then format and page count",
        "what_you_learn": ["about 9 short strings, each one concrete thing the reader gets"],
        "who_for": "HTML <ul> of 4-6 kinds of reader this book fits",
        "faq": [{"question": "5-7 real questions a buyer would ask", "answer": "short honest answer"}],
        "seo_title": "…",
        "meta_description": "…",
    }
    text = pdf.get("head") or ""
    if not text.strip():
        material = ("(The tool could not read text from this PDF - it may be a scanned book. "
                    "ATTACH THE PDF to this message and read it before writing.)")
    else:
        material = "--- START OF BOOK (front matter, contents, opening) ---\n" + text
        if pdf.get("tail"):
            material += "\n\n--- END OF BOOK (closing pages) ---\n" + pdf["tail"]
    return f"""You are writing a store listing for an ebook.

{_RULES}
- Delivery wording must be exactly true: it is a PDF; after payment the buyer signs in to the Account page on the site and presses Download. Do not promise delivery by email.
- The FAQ must include how the buyer receives the file.

Book title: {title}
Format: PDF ebook, {pdf.get('pages') or 'unknown number of'} pages
Price: ${price:.2f}

Return JSON with exactly these keys:
{json.dumps(schema, ensure_ascii=False, indent=2)}

{material}
"""


def pod_prompt(item: dict) -> str:
    schema = {
        "description": "HTML, 1-2 short paragraphs: what the product is and the design on it",
        "bible_inspiration": "HTML: one fitting Bible verse (book chapter:verse in <strong>) quoted accurately, "
                             "plus one sentence linking it to the design. Empty string if no verse clearly fits",
        "story_behind_design": "HTML, one short paragraph about the idea of the design",
        "product_info": "HTML with material / print facts taken ONLY from the Spring text below. Empty string if none",
        "seo_title": "…",
        "meta_description": "…",
    }
    return f"""You are writing a store listing for a print-on-demand product sold through Spring.

{_RULES}
- Quote Bible verses accurately and name the translation only if you are sure of it.
- The product is printed and shipped by Spring; do not promise delivery times.
- If product photos are attached to this message, describe the design from them.

Product title: {item.get('title', '')}
Category: {item.get('category', '')}
Price: ${float(item.get('price') or 0):.2f}
Spring page: {item.get('spring_url', '')}
Text on the Spring page: {item.get('source_text') or '(none)'}

Return JSON with exactly these keys:
{json.dumps(schema, ensure_ascii=False, indent=2)}
"""


def _plain(html: str, limit: int = 1500) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return _cut(text.replace("&nbsp;", " "), limit)


def design_prompt(item: dict, product: dict) -> str:
    """A design (the attached picture) printed on a Printify product. product = the site's pod_blueprint
    answer: title, brand, model, description (the blank's facts), embroidery."""
    method = "embroidered" if product.get("embroidery") else "printed"
    schema = {
        "title": "store name of the product, under 60 characters: the design idea + the product type "
                 f"(for example \"Lion of Judah {('Embroidered ' if product.get('embroidery') else '')}T-Shirt\")",
        "description": "HTML, 1-2 short paragraphs: the design on it and what the product is",
        "bible_inspiration": "HTML: one fitting Bible verse (book chapter:verse in <strong>) quoted accurately, "
                             "plus one sentence linking it to the design. Empty string if no verse clearly fits",
        "story_behind_design": "HTML, one short paragraph about the idea of the design",
        "product_info": "HTML <ul> of material / fit / care facts taken ONLY from the product facts below",
        "seo_title": "…",
        "meta_description": "…",
    }
    colors = ", ".join(item.get("color_names") or []) or "(not chosen yet)"
    return f"""You are writing a store listing for a print-on-demand product.
THE DESIGN IS THE PICTURE ATTACHED TO THIS MESSAGE: look at it and describe what it really shows.

{_RULES}
- Quote Bible verses accurately and name the translation only if you are sure of it.
- The item is made to order and {method} by our print partner, then shipped; do not promise delivery times.
- Do not mention Printify, the brand of the blank or the price in the title.

Design file name: {Path(item.get('file') or '').name}
Product: {product.get('title', '')} ({product.get('brand', '')} {product.get('model', '')}), the design is {method} on it
Colors offered: {colors}

Product facts (from the maker of the blank):
{_plain(product.get('description', '')) or '(none)'}

Return JSON with exactly these keys:
{json.dumps(schema, ensure_ascii=False, indent=2)}
"""


# ------------------------------------------------------------------ reading the answer
def clean_html(html: str) -> str:
    html = re.sub(r"<(script|style|iframe)\b.*?</\1\s*>", "", html, flags=re.S | re.I)
    html = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html, flags=re.I)
    html = re.sub(r"(href|src)\s*=\s*([\"']?)\s*javascript:[^\"'>\s]*\2", "", html, flags=re.I)
    return html.replace("&nbsp;", " ").replace(" ", " ").strip()


def _cut(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    head = text[:limit + 1]
    return (head.rsplit(" ", 1)[0] if " " in head else text[:limit]).rstrip(" ,;:-")


def _find_json(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Không thấy JSON trong nội dung dán vào. Hãy dán nguyên câu trả lời của Claude/ChatGPT "
                         "(phần bắt đầu bằng { và kết thúc bằng }).")
    try:
        data = json.loads(text[start:end + 1])
    except ValueError as exc:
        raise ValueError(f"JSON bị lỗi cú pháp ({exc}). Hãy bảo Claude/ChatGPT “trả lại đúng JSON hợp lệ”.") from exc
    if not isinstance(data, dict):
        raise ValueError("Kết quả phải là một đối tượng JSON { … }.")
    return data


def parse_reply(text: str, kind: str) -> dict:
    """kind: 'ebook' | 'pod' | 'design'. Returns the cleaned listing or raises ValueError (Vietnamese message)."""
    data = _find_json(text)
    keys = {"ebook": EBOOK_KEYS, "pod": POD_KEYS, "design": DESIGN_KEYS}[kind]
    out: dict = {}
    for key, typ in keys.items():
        val = data.get(key)
        if val is None:
            val = typ()
        if not isinstance(val, typ):
            raise ValueError(f"Trường “{key}” sai kiểu dữ liệu.")
        out[key] = val
    missing = [k for k in REQUIRED[kind] if not out[k]]
    if missing:
        raise ValueError("Kết quả thiếu: " + ", ".join(missing) + ". Hãy bảo Claude/ChatGPT viết lại cho đủ.")
    if "…" in (out["seo_title"], out["meta_description"]):
        raise ValueError("Kết quả vẫn là mẫu trống (…). Hãy dán câu trả lời, không phải prompt.")
    for key in ("description", "who_for", "bible_inspiration", "story_behind_design", "product_info"):
        if key in out:
            out[key] = clean_html(out[key])
    for key in ("subtitle", "seo_title", "title"):
        if key in out:
            out[key] = _cut(out[key], {"subtitle": 90, "seo_title": 70, "title": 80}[key])
    out["meta_description"] = _cut(out["meta_description"], 160)
    if kind == "ebook":
        out["what_you_learn"] = [_cut(str(x), 200) for x in out["what_you_learn"] if str(x).strip()]
        faq = []
        for q in out["faq"]:
            if isinstance(q, dict) and str(q.get("question", "")).strip() and str(q.get("answer", "")).strip():
                faq.append({"question": _cut(str(q["question"]), 200), "answer": str(q["answer"]).strip()})
        out["faq"] = faq
    return out
