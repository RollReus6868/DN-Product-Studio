"""Logic tests (no window needed) — run on Linux, Windows and macOS in CI:
python -m unittest discover -s tests -v"""
from __future__ import annotations

import http.server
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
_APPDATA = tempfile.mkdtemp(prefix="dnps_test_")
os.environ["APPDATA"] = _APPDATA
os.environ["DNPS_TOOL_TOKEN"] = "test-token-0123456789abcdefgh"

import requests  # noqa: E402
from PIL import Image  # noqa: E402

import pdfread  # noqa: E402
import prompts  # noqa: E402
import scan  # noqa: E402
import server  # noqa: E402
import spring  # noqa: E402
import storage  # noqa: E402
import webstore  # noqa: E402
from fake_site import TOKEN, FakeSite  # noqa: E402
from selfcheck import tiny_pdf  # noqa: E402

GOOD = {"subtitle": "A study edition", "description": "<p>Hook.</p><h3>Inside</h3><ul><li>One</li></ul>",
        "what_you_learn": ["How the canon formed", "Why it matters"], "who_for": "<ul><li>Readers</li></ul>",
        "faq": [{"question": "How do I get it?", "answer": "Sign in to the Account page and press Download."}],
        "seo_title": "The Book — Dark Network", "meta_description": "An honest study edition."}
POD_GOOD = {"description": "<p>A tee.</p>", "bible_inspiration": "<p><strong>Exodus 13:21</strong> — text</p>",
            "story_behind_design": "<p>Story.</p>", "product_info": "", "seo_title": "Tee", "meta_description": "A tee."}


def make_folder(td: str, names=("The-Book-of-Enoch", "Jubilees_Part-1")) -> None:
    for n in names:
        (Path(td) / f"{n}.pdf").write_bytes(tiny_pdf(f"Opening of {n}"))
        Image.new("RGB", (1055, 1491), "#8a6420").save(Path(td) / f"{n}.png")


class ScanTests(unittest.TestCase):
    def test_pairs_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            make_folder(td)
            (Path(td) / "No-Cover.PDF").write_bytes(tiny_pdf())
            Image.new("RGB", (10, 10)).save(Path(td) / "Lonely.jpg")
            Image.new("RGB", (10, 10)).save(Path(td) / "the-book-of-enoch.JPG")   # other case, same name
            (Path(td) / "notes.txt").write_text("x")
            found = scan.scan_folder(td)
            self.assertEqual([e["title"] for e in found["ebooks"]], ["Jubilees Part 1", "No Cover", "The Book of Enoch"])
            self.assertTrue(all(e["cover"] for e in found["ebooks"] if e["title"] != "No Cover"))
            self.assertEqual(found["no_cover"], ["No-Cover.PDF"])
            self.assertEqual(found["no_pdf"], ["Lonely.jpg"])

    def test_missing_folder(self):
        with self.assertRaises(ValueError):
            scan.scan_folder("/no/such/folder/here")

    def test_slugify(self):
        self.assertEqual(scan.slugify("The Book of Enoch: A Reader's Edition — Part 2"), "the-book-of-enoch-a-reader-s-edition-part-2")
        self.assertEqual(scan.slugify("Sách Đức Tin"), "sach-duc-tin")


class PdfTests(unittest.TestCase):
    def test_reads_text_and_pages(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.pdf"
            p.write_bytes(tiny_pdf("Hello canon"))
            pdf = pdfread.read_pdf(str(p))
            self.assertEqual(pdf["pages"], 1)
            self.assertIn("Hello canon", pdf["head"])
            self.assertEqual(pdf["tail"], "")

    def test_broken_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.pdf"
            p.write_bytes(b"not a pdf")
            with self.assertRaises(ValueError):
                pdfread.read_pdf(str(p))


class PromptTests(unittest.TestCase):
    def test_ebook_prompt_has_the_material(self):
        text = prompts.ebook_prompt("The Book of Enoch", 9.99, {"pages": 212, "head": "CONTENTS Part One", "tail": "Closing"})
        for part in ("The Book of Enoch", "212 pages", "$9.99", "CONTENTS Part One", "Closing", "what_you_learn", "Do not invent reviews"):
            self.assertIn(part, text)

    def test_scanned_pdf_asks_for_attachment(self):
        self.assertIn("ATTACH THE PDF", prompts.ebook_prompt("X", 1, {"pages": 3, "head": "", "tail": ""}))

    def test_parse_plain_fenced_and_chatty(self):
        raw = json.dumps(GOOD)
        for text in (raw, f"```json\n{raw}\n```", f"Here is the listing:\n{raw}\nHope this helps!"):
            self.assertEqual(prompts.parse_reply(text, "ebook")["subtitle"], "A study edition")

    def test_parse_cleans_and_limits(self):
        bad = dict(GOOD, description='<p onclick="x()">Hi&nbsp;there you</p><script>alert(1)</script>',
                   meta_description="word " * 60, faq=[{"question": "", "answer": "x"}, GOOD["faq"][0]])
        out = prompts.parse_reply(json.dumps(bad), "ebook")
        self.assertEqual(out["description"], "<p>Hi there you</p>")
        self.assertLessEqual(len(out["meta_description"]), 160)
        self.assertEqual(len(out["faq"]), 1)

    def test_parse_errors_are_explained(self):
        for text in ("no json here", "{broken", json.dumps({"subtitle": "x"}), json.dumps(dict(GOOD, faq="nope")),
                     json.dumps(dict(GOOD, seo_title="…"))):
            with self.assertRaises(ValueError):
                prompts.parse_reply(text, "ebook")

    def test_pod(self):
        self.assertIn("https://x.creator-spring.com/listing/a", prompts.pod_prompt(
            {"title": "Tee", "category": "Apparel", "price": 25, "spring_url": "https://x.creator-spring.com/listing/a"}))
        self.assertEqual(prompts.parse_reply(json.dumps(POD_GOOD), "pod")["product_info"], "")


class SpringTests(unittest.TestCase):
    def test_json_ld(self):
        page = """<html><head><title>x</title><script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[{"@type":"Product","name":"Lion of Judah Mug",
        "description":"<b>11oz</b> ceramic","image":["https://cdn/a.jpg",{"url":"https://cdn/b.jpg"}],
        "offers":{"@type":"Offer","price":"18.50","priceCurrency":"USD"}}]}</script></head></html>"""
        info = spring.parse_page(page, "https://s/l")
        self.assertEqual((info["title"], info["price"], info["images"], info["category"], info["source_text"]),
                         ("Lion of Judah Mug", 18.5, ["https://cdn/a.jpg", "https://cdn/b.jpg"], "Mugs", "11oz ceramic"))

    def test_open_graph_fallback(self):
        page = """<meta property="og:title" content="Exodus Route Tee | Spring"><meta content="https://cdn/t.png" property="og:image">
        <meta property="og:description" content="Soft &amp; warm"><meta property="product:price:amount" content="27,99">"""
        info = spring.parse_page(page, "https://s/l")
        self.assertEqual((info["title"], info["price"], info["images"], info["category"], info["source_text"]),
                         ("Exodus Route Tee", 27.99, ["https://cdn/t.png"], "Apparel", "Soft & warm"))

    def test_empty_page(self):
        info = spring.parse_page("<html><div id=root></div></html>", "https://s/l")
        self.assertEqual((info["title"], info["images"], info["price"]), ("", [], 0.0))

    def test_category(self):
        self.assertEqual(spring.guess_category("Daniel's Visions Poster"), "Wall Art")
        self.assertEqual(spring.guess_category("Sticker pack"), "Gifts")

    def test_bad_link(self):
        with self.assertRaises(ValueError):
            spring.fetch("spring.com/x")


class _Img(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        buf = io.BytesIO()
        Image.new("RGB", (800, 800), "#224466").save(buf, "PNG")
        self.send_response(200 if self.path.endswith(".png") else 404)
        self.send_header("Content-Length", str(len(buf.getvalue())))
        self.end_headers()
        self.wfile.write(buf.getvalue())

    def log_message(self, *a):
        pass


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.site = FakeSite()
        self.addCleanup(self.site.close)
        self.client = webstore.SiteClient(self.site.api, TOKEN)
        self.td = tempfile.mkdtemp()
        make_folder(self.td, ("The-Book-of-Enoch",))
        eb = scan.scan_folder(self.td)["ebooks"][0]
        self.item = {**eb, "price": 9.99, "listing": dict(GOOD)}
        self.cfg = {"shared_variant_id": "2204367"}

    def test_ebook_draft_private_pdf_and_small_cover(self):
        web = webstore.publish_ebook(self.item, self.cfg, self.client)
        rec = self.site.records["Ebook"][0]
        self.assertEqual((web["status"], rec["status"], rec["slug"]), ("draft", "draft", "the-book-of-enoch"))
        self.assertEqual((rec["price"], rec["lemon_squeezy_variant_id"]), (9.99, "2204367"))
        self.assertRegex(rec["secure_file_uri"], r"^[0-9a-f]{8}_The-Book-of-Enoch\.pdf$")
        self.assertIn("/public-files/", rec["cover_image"])
        self.assertEqual(rec["faq"], GOOD["faq"])
        cover, pdf = self.site.files
        self.assertEqual((cover["private"], cover["name"], cover["head"][:2]), (False, "the-book-of-enoch.jpg", b"\xff\xd8"))
        self.assertEqual((pdf["private"], pdf["name"], pdf["head"]), (True, "The-Book-of-Enoch.pdf", b"%PDF"))

    def test_republish_updates_without_reupload_and_keeps_status(self):
        webstore.publish_ebook(self.item, self.cfg, self.client)
        self.site.records["Ebook"][0]["status"] = "published"
        self.item["price"] = 12.5
        self.item["title"] = "Renamed"          # the web address must not change after the first publish
        web = webstore.publish_ebook(self.item, self.cfg, self.client)
        rec = self.site.records["Ebook"][0]
        self.assertEqual((len(self.site.files), len(self.site.records["Ebook"])), (2, 1))
        self.assertEqual((rec["price"], rec["title"], rec["slug"], rec["status"], web["status"]),
                         (12.5, "Renamed", "the-book-of-enoch", "published", "published"))

    def test_existing_record_is_not_overwritten_silently(self):
        self.site.records["Ebook"].append({"id": "live1", "title": "Live book", "slug": "the-book-of-enoch",
                                           "status": "published", "description": "<p>hand written</p>"})
        with self.assertRaises(webstore.SiteError) as cm:
            webstore.publish_ebook(self.item, self.cfg, self.client)
        self.assertEqual(cm.exception.code, "exists")
        self.assertEqual(self.site.records["Ebook"][0]["description"], "<p>hand written</p>")
        self.assertEqual(len(self.site.files), 2)
        web = webstore.publish_ebook(self.item, self.cfg, self.client, overwrite=True)
        self.assertEqual((web["id"], web["status"], len(self.site.files)), ("live1", "published", 2))
        self.assertEqual(self.site.records["Ebook"][0]["description"], GOOD["description"])

    def test_errors(self):
        with self.assertRaises(webstore.SiteError) as cm:
            webstore.SiteClient(self.site.api, "wrong-token-000000000000000").ping()
        self.assertEqual(cm.exception.code, "auth")
        with self.assertRaises(webstore.SiteError) as cm:
            webstore.SiteClient(self.site.api, "").ping()
        self.assertEqual(cm.exception.code, "no_token")
        with self.assertRaises(webstore.SiteError) as cm:
            webstore.SiteClient(self.site.base + "/nope", TOKEN).ping()
        self.assertEqual(cm.exception.code, "not_deployed")
        self.site.fail_upload = True
        with self.assertRaises(webstore.SiteError) as cm:
            webstore.publish_ebook(self.item, self.cfg, self.client)
        self.assertEqual(cm.exception.code, "too_large")
        with self.assertRaises(webstore.SiteError) as cm:
            webstore.publish_ebook({**self.item, "listing": None}, self.cfg, self.client)
        self.assertEqual(cm.exception.code, "incomplete")

    def test_restore_pdf_of_a_book_copied_from_the_old_site(self):
        self.site.records["Ebook"] += [
            {"id": "a", "title": "Jubilees Part 0", "slug": "j0", "status": "published",
             "secure_file_uri": "mp/private/6aa80a39/2ee2042ac_The-Book-of-Enoch.pdf"},
            {"id": "b", "title": "Already fine", "slug": "ok", "status": "published", "secure_file_uri": "0000000a_x.pdf"}]
        self.assertEqual(self.client.pending_pdfs(), [{"title": "Jubilees Part 0", "file_name": "The-Book-of-Enoch.pdf"}])
        self.assertEqual(webstore.restore_pdf(self.item["pdf"], self.client), ["Jubilees Part 0"])
        self.assertRegex(self.site.records["Ebook"][0]["secure_file_uri"], r"^[0-9a-f]{8}_The-Book-of-Enoch\.pdf$")
        self.assertEqual((self.site.files[0]["private"], self.site.files[0]["head"]), (True, b"%PDF"))
        self.assertEqual(self.client.pending_pdfs(), [])

    def test_pod(self):
        img = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Img)
        threading.Thread(target=img.serve_forever, daemon=True).start()
        self.addCleanup(img.server_close)
        self.addCleanup(img.shutdown)
        base = f"http://127.0.0.1:{img.server_address[1]}"
        item = {"id": "u", "title": "Lion of Judah Mug", "price": 18, "category": "Mugs", "spring_url": "https://s/l",
                "images": [f"{base}/a.png", f"{base}/b.png"], "listing": dict(POD_GOOD)}
        web = webstore.publish_pod(item, {}, self.client)
        rec = self.site.records["Product"][0]
        self.assertEqual((web["status"], rec["slug"], rec["category"], len(rec["images"]), rec["spring_url"]),
                         ("draft", "lion-of-judah-mug", "Mugs", 2, "https://s/l"))
        self.assertTrue(all(f["head"][:2] == b"\xff\xd8" and not f["private"] for f in self.site.files))
        webstore.publish_pod(item, {}, self.client)
        self.assertEqual(len(self.site.files), 2, "unchanged photos are not uploaded again")
        item["images"] = [f"{base}/missing.gif"]
        with self.assertRaises(webstore.SiteError):
            webstore.publish_pod(item, {}, self.client)


class ServerTests(unittest.TestCase):
    """The same calls the window makes, end to end against the stand-in website."""

    @classmethod
    def setUpClass(cls):
        cls.site = FakeSite()
        storage.save_config({"site_api_url": cls.site.api})
        cls.srv, cls.url = server.start()
        cls.td = tempfile.mkdtemp()
        make_folder(cls.td)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.site.close()

    def call(self, path, body=None, key=None, status=200):
        r = requests.post(self.url + path.lstrip("/"), json=body or {}, headers={"X-Session": key or server.KEY}, timeout=30)
        self.assertEqual(r.status_code, status, r.text)
        return r.json()

    def test_full_ebook_flow(self):
        self.assertIn("error", self.call("/api/state", key="wrong", status=403))
        page = requests.get(self.url, timeout=10).text
        self.assertIn(server.KEY, page)
        self.assertNotIn("__SESSION_KEY__", page)

        self.call("/api/config", {"default_price": 9.99})
        st = self.call("/api/ebooks/scan", {"folder": self.td})
        self.assertEqual([e["title"] for e in st["ebooks"]], ["Jubilees Part 1", "The Book of Enoch"])
        eb = st["ebooks"][1]
        self.assertEqual((eb["price"], eb["has_listing"], eb["web_status"], eb["has_cover"]), (9.99, False, "", True))
        self.assertEqual(requests.get(self.url + "api/cover", params={"k": server.KEY, "id": eb["id"]}, timeout=10).content[:2], b"\xff\xd8")
        self.assertEqual(requests.get(self.url + "api/cover", params={"k": "x", "id": eb["id"]}, timeout=10).status_code, 403)

        self.assertEqual(self.call("/api/item/update", {"kind": "ebook", "id": eb["id"], "price": "12,5"})["item"]["price"], 12.5)
        self.call("/api/item/update", {"kind": "ebook", "id": eb["id"], "price": "abc"}, status=400)
        self.call("/api/item/update", {"kind": "ebook", "id": eb["id"], "title": " "}, status=400)

        pr = self.call("/api/item/prompt", {"kind": "ebook", "id": eb["id"]})
        self.assertIn("Opening of The-Book-of-Enoch", pr["prompt"])
        self.assertIn("$12.50", pr["prompt"])
        self.assertEqual((pr["pages"], pr["attach"]), (1, ""))

        self.assertEqual(self.call("/api/item/publish", {"kind": "ebook", "id": eb["id"]}, status=400)["code"], "incomplete")
        self.assertIn("JSON", self.call("/api/item/reply", {"kind": "ebook", "id": eb["id"], "text": "oops"}, status=400)["error"])
        self.assertTrue(self.call("/api/item/reply", {"kind": "ebook", "id": eb["id"], "text": json.dumps(GOOD)})["item"]["has_listing"])
        self.assertEqual(self.call("/api/item/listing", {"kind": "ebook", "id": eb["id"]})["listing"]["seo_title"], GOOD["seo_title"])

        self.assertEqual(self.call("/api/site/ping")["site"], "Dark Network (giả lập)")
        item = self.call("/api/item/publish", {"kind": "ebook", "id": eb["id"]})["item"]
        self.assertEqual((item["web_status"], item["slug"]), ("draft", "the-book-of-enoch"))
        self.assertEqual(self.site.records["Ebook"][0]["price"], 12.5)

        # a book copied from the old site: its PDF is in this folder under the original name
        self.site.records["Ebook"].append({"id": "old", "title": "Old Jubilees", "slug": "old-j", "status": "published",
                                           "secure_file_uri": "mp/private/6aa80a39/9f1_jubilees_part-1.pdf"})
        self.site.records["Ebook"].append({"id": "old2", "title": "Not here", "slug": "old-2", "status": "published",
                                           "secure_file_uri": "mp/private/6aa80a39/9f2_Missing.pdf"})
        self.assertEqual(self.call("/api/restore/list")["items"], [
            {"title": "Old Jubilees", "file_name": "jubilees_part-1.pdf", "found": True},
            {"title": "Not here", "file_name": "Missing.pdf", "found": False}])
        self.assertEqual(self.call("/api/restore/one", {"file_name": "jubilees_part-1.pdf"})["attached"], ["Old Jubilees"])
        self.call("/api/restore/one", {"file_name": "Missing.pdf"}, status=400)
        self.assertEqual([i["file_name"] for i in self.call("/api/restore/list")["items"]], ["Missing.pdf"])

        # state survives a restart of the tool (it is stored on disk) and a rescan keeps the work
        again = self.call("/api/ebooks/scan", {"folder": self.td})["ebooks"][1]
        self.assertEqual((again["has_listing"], again["web_status"], again["price"], again["pages"]), (True, "draft", 12.5, 1))

    def test_orders_and_traffic_are_passed_through(self):
        self.site.orders = [{"order_id": "9001", "date": "2026-10-07T03:00:00Z", "email": "a@b.c", "status": "paid",
                             "currency": "USD", "buyer": "guest", "total": 3198, "items": ["Book 1", "Book 2"]}]
        self.site.traffic = {"summary": {"visitors_today": 2, "views_today": 5}, "days": [{"day": "2026-10-07", "views": 5, "visitors": 2}],
                             "pages": [{"path": "/books", "views": 3, "visitors": 2}]}
        self.assertEqual(self.call("/api/orders")["items"], self.site.orders)
        self.assertEqual(self.call("/api/traffic"), self.site.traffic)

    def test_config_validation(self):
        self.assertEqual(self.call("/api/config", {"shared_variant_id": " 2204367 ", "default_price": "7.5"})["config"]["shared_variant_id"], "2204367")
        self.assertEqual(storage.load_config()["default_price"], 7.5)
        self.call("/api/config", {"shared_variant_id": "abc"}, status=400)
        self.call("/api/config", {"default_price": "0"}, status=400)
        self.call("/api/open", {"url": "file:///etc/passwd"}, status=400)
        self.call("/api/pods/add", {"urls": ""}, status=400)
        self.assertEqual(requests.get(self.url + "../storage.py", timeout=10).status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
