"""Drive the real UI in headless Chromium against the real local server and a
stand-in website; save screenshots; fail on console errors or overflow.

    python tests/smoke_ui.py <output-folder>

Needs the `playwright` package and a Chromium (not part of the app; dev only).
"""
from __future__ import annotations

import http.server
import io
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="dnps_shots_"))
OUT.mkdir(parents=True, exist_ok=True)

from PIL import Image, ImageDraw  # noqa: E402


class Extra(http.server.BaseHTTPRequestHandler):
    """Fake Spring product pages + photos, and a fake GitHub 'latest release'."""

    def do_GET(self):  # noqa: N802
        base = f"http://127.0.0.1:{self.server.server_address[1]}"
        if self.path.startswith("/listing/"):
            name = self.path.split("/")[-1].replace("-", " ").title()
            body = f"""<html><head><script type="application/ld+json">{json.dumps({
                "@type": "Product", "name": name, "description": "Printed on demand. 100% cotton.",
                "image": [f"{base}/img/{i}.png" for i in (1, 2, 3)], "offers": {"price": "24.99"}})}</script></head></html>""".encode()
        elif self.path.startswith("/img/"):
            buf = io.BytesIO()
            im = Image.new("RGB", (800, 800), "#1d2433")
            ImageDraw.Draw(im).ellipse((200, 200, 600, 600), fill="#c79a3a")
            im.save(buf, "PNG")
            body = buf.getvalue()
        elif "/releases/latest" in self.path:
            body = json.dumps({"tag_name": "v9.9.9", "body": "Thêm trang POD, sửa lỗi nhỏ.",
                               "html_url": "https://github.com/x/y/releases", "assets": []}).encode()
        else:
            body = b""
        self.send_response(200 if body else 404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


extra = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Extra)
threading.Thread(target=extra.serve_forever, daemon=True).start()
EXTRA = f"http://127.0.0.1:{extra.server_address[1]}"

os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="dnps_ui_")
os.environ["DNPS_TOOL_TOKEN"] = "test-token-0123456789abcdefgh"
os.environ["DNPS_UPDATE_API"] = EXTRA

from fake_site import FakeSite  # noqa: E402
from test_core import GOOD, POD_GOOD  # noqa: E402  (also points APPDATA at a temp folder first)

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="dnps_ui_")
import server  # noqa: E402
import storage  # noqa: E402
from selfcheck import tiny_pdf  # noqa: E402

site = FakeSite()
storage.save_config({"site_base": site.base})
_srv, URL = server.start()

books = Path(tempfile.mkdtemp(prefix="BOOK_"))
for i, (name, color) in enumerate([("The-Book-of-Enoch_A-Black-Readers-Study-Edition", "#3b2a1a"), ("Jubilees_Part-1-Counted-and-Allotted", "#1f3a36"),
                                   ("The-Ethiopian-Canon", "#3a1f2b"), ("Enoch-Companion-Notes", "#22304d")]):
    (books / f"{name}.pdf").write_bytes(tiny_pdf(f"Opening pages of {name}"))
    if i != 3:   # one book without a cover, to show the warning
        im = Image.new("RGB", (1055, 1491), color)
        ImageDraw.Draw(im).rectangle((120, 200, 935, 1290), outline="#c79a3a", width=14)
        im.save(books / f"{name}.png")

errors: list[str] = []


def main() -> int:
    from playwright.sync_api import sync_playwright

    exe = next(iter(sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))), None)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(exe) if exe else None)
        for width, height in ((1200, 800), (900, 620)):
            ctx = browser.new_context(viewport={"width": width, "height": height}, permissions=["clipboard-read", "clipboard-write"])
            page = ctx.new_page()
            page.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" and "status of 400" not in m.text else None)   # 400 = a refusal the UI shows on purpose
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            tag = f"{width}x{height}"

            def shot(name):
                page.wait_for_timeout(350)
                over = page.evaluate("""() => { const w = innerWidth; const bad = [];
                    for (const el of document.querySelectorAll('.main *, .sidebar *, .dialog *')) { const r = el.getBoundingClientRect();
                      if (r.width && (r.right > w + 1 || r.left < -1)) bad.push(el.className || el.tagName); }
                    return { sw: document.documentElement.scrollWidth, w, bad: bad.slice(0, 5),
                             hscroll: [...document.querySelectorAll('.page-body, .dialog-body')].filter(e => e.scrollWidth > e.clientWidth + 1).length }; }""")
                if over["sw"] > over["w"] or over["bad"] or over["hscroll"]:
                    errors.append(f"{tag} {name}: overflow {over}")
                page.screenshot(path=str(OUT / f"{tag}_{name}.png"))

            page.goto(URL)
            page.wait_for_selector("[data-nav]")
            first = width == 1200
            if first:
                shot("01_ebook_empty")
                page.fill("#folder", str(books))
                page.click('[data-act="scan"]')
                page.wait_for_selector(".item")
                assert page.locator(".item").count() == 4
                shot("02_ebook_scanned")
                # edit the price inline
                price = page.locator(".item").nth(2).locator('[data-field="price"]')
                price.fill("26,99")
                price.press("Enter")
                page.wait_for_timeout(300)
                assert price.input_value() == "26.99", price.input_value()
                # write descriptions: copy prompt, paste answer; the dialog walks through the list
                page.locator(".item").first.locator('[data-act="write"]').click()
                page.wait_for_selector("#w-reply")
                shot("03_writer")
                page.click('[data-act="w-copy"]')
                clip = page.evaluate("navigator.clipboard.readText()")
                assert "Return JSON with exactly these keys" in clip and "Opening pages of" in clip, clip[:200]
                page.fill("#w-reply", "not json")
                page.click('[data-act="w-save"]')
                page.wait_for_function("document.querySelector('#w-error').textContent.length > 0")
                shot("04_writer_error")
                for _ in range(4):
                    page.wait_for_selector("#w-reply")
                    page.fill("#w-reply", json.dumps(GOOD, indent=1))
                    page.click('[data-act="w-save"]')
                    page.wait_for_timeout(500)
                page.wait_for_function("!document.querySelector('.dialog')")
                assert page.locator(".pill.warn").count() == 0
                # publish everything that is complete (3 of 4: one has no cover)
                page.click('[data-act="publish-all"]')
                page.wait_for_function("document.querySelectorAll('.pill.info').length === 3", timeout=60000)
                assert len(site.records["Ebook"]) == 3 and all(r["status"] == "draft" for r in site.records["Ebook"])
                page.wait_for_timeout(4500)   # let the toast go
                shot("05_ebook_published")
                # a record that already exists on the web asks before overwriting
                for r in site.records["Ebook"]:
                    r["id"] += "-recreated"
                page.locator(".item").nth(1).locator('[data-act="publish"]').click()
                page.wait_for_selector("#c-yes")
                shot("05b_confirm_overwrite")
                page.click("#c-yes")
                page.wait_for_function("!document.querySelector('.dialog')")
                page.wait_for_timeout(800)
                assert not page.locator(".item-error").count()
            page.click('[data-nav="pod"]')
            if first:
                shot("06_pod_empty")
                page.fill("#urls", f"{EXTRA}/listing/lion-of-judah-mug\n{EXTRA}/listing/exodus-route-t-shirt\n{EXTRA}/nothing-here")
                page.click('[data-act="pods-add"]')
                page.wait_for_selector(".item")
                page.wait_for_function("document.querySelectorAll('.item').length === 2")
                assert page.input_value("#urls").strip() == f"{EXTRA}/nothing-here"
                page.locator(".item").first.locator('[data-act="write"]').click()
                for _ in range(2):
                    page.wait_for_selector("#w-reply")
                    page.fill("#w-reply", json.dumps(POD_GOOD))
                    page.click('[data-act="w-save"]')
                    page.wait_for_timeout(500)
                page.click('[data-act="publish-all"]')
                page.wait_for_function("document.querySelectorAll('.pill.info').length === 2", timeout=60000)
                assert [r["category"] for r in site.records["Product"]] == ["Mugs", "Apparel"], site.records["Product"]
                page.wait_for_timeout(4500)
            shot("07_pod")
            page.click('[data-nav="settings"]')
            page.click('[data-act="ping"]')
            page.wait_for_selector(".note.ok")
            page.click('[data-act="update-check"]')
            page.wait_for_selector(".note.info")
            shot("08_settings")
            page.evaluate("document.querySelector('.page-body').scrollTop = 99999")
            shot("09_settings_bottom")
            page.click('[data-nav="guide"]')
            shot("10_guide")
            # light mode + another theme + collapsed sidebar
            page.click('[data-act="mode"]')
            page.click('[data-nav="ebook"]')
            shot("11_ebook_light")
            page.locator(".item").first.locator('[data-act="write"]').click()
            page.wait_for_selector("#w-reply")
            shot("12_writer_light")
            page.click('[data-act="close"]')
            page.click('[data-nav="settings"]')
            shot("13_settings_light")
            page.click('[data-act="sidebar"]')
            page.click('[data-nav="pod"]')
            shot("14_pod_light_collapsed")
            page.click('[data-act="sidebar"]')
            page.click('[data-act="mode"]')
            ctx.close()
        browser.close()
    for e in errors:
        print("ERROR", e)
    print("screenshots in", OUT)
    print("smoke_ui:", "FAIL" if errors else "OK")
    return 1 if errors else 0


if __name__ == "__main__":
    code = main()
    os._exit(code)
