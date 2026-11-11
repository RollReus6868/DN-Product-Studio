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
import shrink  # noqa: E402
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
        self.cfg = {"pdf_shrink": "safe"}

    def test_ebook_draft_private_pdf_and_small_cover(self):
        web = webstore.publish_ebook(self.item, self.cfg, self.client)
        rec = self.site.records["Ebook"][0]
        self.assertEqual((web["status"], rec["status"], rec["slug"]), ("draft", "draft", "the-book-of-enoch"))
        self.assertEqual(rec["price"], 9.99)
        self.assertNotIn("lemon_squeezy_variant_id", rec)
        self.assertRegex(rec["secure_file_uri"], r"^[0-9a-f]{8}_The-Book-of-Enoch\.pdf$")
        self.assertIn("/public-files/", rec["cover_image"])
        self.assertEqual(rec["faq"], GOOD["faq"])
        cover, pdf = self.site.files
        self.assertEqual((cover["private"], cover["name"], cover["head"]), (False, "the-book-of-enoch.webp", b"RIFF"))
        self.assertEqual((pdf["private"], pdf["name"], pdf["head"]), (True, "The-Book-of-Enoch.pdf", b"%PDF"))
        self.assertTrue(cover["cache_field"], "uploads ask browsers to keep the file for a year")

    def test_cover_is_shrunk_to_the_size_the_site_shows(self):
        from PIL import Image
        with Image.open(io.BytesIO(webstore.cover_webp(self.item["cover"], webstore.COVER_BOX))) as im:
            self.assertEqual(im.format, "WEBP")
            self.assertLessEqual((im.width, im.height), webstore.COVER_BOX)

    def test_pdf_is_compressed_before_upload_unless_turned_off(self):
        bloated_pdf(Path(self.item["pdf"]))
        size = os.path.getsize(self.item["pdf"])
        web = webstore.publish_ebook(self.item, self.cfg, self.client)
        pdf = self.site.files[1]
        self.assertEqual((pdf["name"], pdf["head"]), ("The-Book-of-Enoch.pdf", b"%PDF"))
        self.assertLess(pdf["size"], size)
        self.assertEqual(web["pdf_sizes"], {"before": size, "after": pdf["size"]})
        # off: the file goes up exactly as it is
        os.utime(self.item["pdf"], ns=(1, 1))
        webstore.publish_ebook(self.item, {"pdf_shrink": "off"}, self.client)
        self.assertEqual(self.site.files[2]["size"], size)
        # restoring a PDF of a copied book is compressed too
        self.site.records["Ebook"].append({"id": "a", "title": "Old", "slug": "old", "status": "published",
                                           "secure_file_uri": "mp/private/6aa80a39/2ee2042ac_The-Book-of-Enoch.pdf"})
        webstore.restore_pdf(self.item["pdf"], self.client, {"pdf_shrink": "strong"})
        self.assertLess(self.site.files[3]["size"], pdf["size"])

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
        self.assertTrue(all(f["head"] == b"RIFF" and f["name"].endswith(".webp") and not f["private"] for f in self.site.files))
        webstore.publish_pod(item, {}, self.client)
        self.assertEqual(len(self.site.files), 2, "unchanged photos are not uploaded again")
        item["images"] = [f"{base}/missing.gif"]
        with self.assertRaises(webstore.SiteError):
            webstore.publish_pod(item, {}, self.client)


def bloated_pdf(path: Path, pages: int = 4) -> None:
    """A PDF written without compression and with a big photo on every page (like many exported books)."""
    from pypdf import PdfWriter
    from pypdf.generic import ContentStream, DecodedStreamObject, NameObject

    photo = io.BytesIO()
    Image.radial_gradient("L").resize((2400, 3200)).convert("RGB").save(photo, "PDF", resolution=300)
    from pypdf import PdfReader
    w = PdfWriter()
    for i in range(pages):
        w.add_page(PdfReader(io.BytesIO(photo.getvalue())).pages[0])
        text = DecodedStreamObject()
        text.set_data((f"BT /F1 12 Tf 72 72 Td (Page {i} " + "lorem ipsum " * 300 + ") Tj ET\n").encode() * 20)
        w.pages[-1][NameObject("/Contents")] = w._add_object(text)
    with open(path, "wb") as f:
        w.write(f)


class ShrinkTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())

    def test_pictures_become_small_webp(self):
        Image.new("RGBA", (3000, 4500), (20, 40, 80, 255)).save(self.td / "big.png")
        data = shrink.web_image(str(self.td / "big.png"), shrink.COVER_BOX)
        with Image.open(io.BytesIO(data)) as im:
            self.assertEqual((im.format, im.size, im.mode), ("WEBP", (640, 960), "RGB"))
        Image.new("RGB", (300, 200)).save(self.td / "small.jpg")
        with Image.open(io.BytesIO(shrink.web_image((self.td / "small.jpg").read_bytes()))) as im:
            self.assertEqual(im.size, (300, 200), "never enlarged")

    def test_pdf_lossless_keeps_pages_and_text(self):
        bloated_pdf(self.td / "b.pdf")
        data, before, after = shrink.shrink_pdf(str(self.td / "b.pdf"))
        self.assertIsNotNone(data)
        self.assertLess(after, before)
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        self.assertEqual(len(r.pages), 4)
        self.assertIn(b"(Page 3 lorem ipsum", r.pages[3].get_contents().get_data())
        # the photos are untouched in lossless mode
        self.assertEqual(r.pages[0].images[0].image.size, (2400, 3200))

    def test_pdf_strong_shrinks_photos(self):
        bloated_pdf(self.td / "b.pdf")
        safe = shrink.shrink_pdf(str(self.td / "b.pdf"))[2]
        data, _before, strong = shrink.shrink_pdf(str(self.td / "b.pdf"), strong=True)
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        self.assertLess(strong, safe)
        self.assertEqual(len(r.pages), 4)
        self.assertLessEqual(max(r.pages[0].images[0].image.size), shrink.STRONG_MAX_SIDE)

    def test_pdf_that_cannot_be_improved_or_read_is_kept(self):
        (self.td / "t.pdf").write_bytes(tiny_pdf())
        self.assertEqual(shrink.shrink_pdf(str(self.td / "t.pdf"))[0], None)
        (self.td / "x.pdf").write_bytes(b"%PDF-1.4 not really")
        data, before, after = shrink.shrink_pdf(str(self.td / "x.pdf"))
        self.assertEqual((data, before, after), (None, 19, 19))


class LightenTests(unittest.TestCase):
    """Re-saving the pictures already on the site as WebP (Cài đặt › Nén lại ảnh trên web)."""

    def setUp(self):
        self.site = FakeSite()
        self.addCleanup(self.site.close)
        self.client = webstore.SiteClient(self.site.api, TOKEN)

    def _put(self, name: str, size=(1600, 2400)) -> str:
        buf = io.BytesIO()
        Image.radial_gradient("L").resize(size).convert("RGB").save(buf, "JPEG", quality=97)
        return self.client.upload(name, buf.getvalue(), False)

    def test_heavy_pictures_are_replaced_and_others_left_alone(self):
        jpg = self._put("old-cover.jpg")
        webp = self._put("done.webp")
        p1, p2 = self._put("mug-1.jpg"), self._put("mug-2.jpg")
        self.site.records["Ebook"] += [
            {"id": "e1", "title": "Heavy", "slug": "h", "status": "published", "cover_image": jpg},
            {"id": "e2", "title": "Already light", "slug": "l", "status": "published", "cover_image": webp},
            {"id": "e3", "title": "Site picture", "slug": "s", "status": "published",
             "cover_image": "https://darknetworkofficial.uk/img/opt/a-640.webp"},
            {"id": "e4", "title": "Other site", "slug": "o", "status": "draft", "cover_image": "https://example.com/a.jpg"}]
        self.site.records["Product"].append({"id": "p1", "title": "Mug", "slug": "m", "status": "draft", "images": [p1, p2]})
        uploads = len(self.site.files)
        seen = []
        out = webstore.lighten_site_pictures(self.client, lambda n, t, title: seen.append((n, t, title)))
        self.assertEqual((out["done"], out["skipped"], out["failed"]), (2, 3, []))
        self.assertLess(out["after"], out["before"])
        self.assertEqual(seen, [(1, 2, "Heavy"), (2, 2, "Mug")])
        e1, e2, e3, e4 = self.site.records["Ebook"]
        self.assertRegex(e1["cover_image"], r"/public-files/[0-9a-f]{8}_old-cover\.webp$")
        self.assertEqual((e2["cover_image"], e3["cover_image"], e4["cover_image"]),
                         (webp, "https://darknetworkofficial.uk/img/opt/a-640.webp", "https://example.com/a.jpg"))
        prod = self.site.records["Product"][0]["images"]
        self.assertTrue(all(u.endswith(".webp") for u in prod) and len(prod) == 2)
        new = self.site.files[uploads:]
        self.assertEqual(len(new), 3)
        with Image.open(io.BytesIO(self.site.blobs[e1["cover_image"][len(self.site.base):]])) as im:
            self.assertEqual((im.format, im.size), ("WEBP", (640, 960)))
        # a second run has nothing left to do
        self.assertEqual(webstore.lighten_site_pictures(self.client)["done"], 0)

    def test_a_missing_picture_is_reported_not_fatal(self):
        self.site.records["Ebook"].append({"id": "e1", "title": "Gone", "slug": "g", "status": "draft",
                                           "cover_image": f"{self.site.base}/storage/v1/object/public/public-files/x_gone.jpg"})
        out = webstore.lighten_site_pictures(self.client)
        self.assertEqual((out["done"], len(out["failed"])), (0, 1))
        self.assertIn("Gone", out["failed"][0])


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

    def test_orders_and_analytics_are_passed_through(self):
        self.site.orders = [{"order_id": "9001", "date": "2026-10-07T03:00:00Z", "email": "a@b.c", "status": "paid",
                             "currency": "USD", "buyer": "guest", "total": 3198, "items": ["Book 1", "Book 2"]}]
        self.site.analytics = {"summary": {"users": 2, "views": 5}, "pages": [{"path": "/books", "views": 3, "users": 2}]}
        self.assertEqual(self.call("/api/orders")["items"], self.site.orders)
        self.assertEqual(self.call("/api/analytics", {"days": 28}), {**self.site.analytics, "days_range": 28})
        self.call("/api/analytics", {"days": 5})   # only 7 / 28 / 90 days
        self.call("/api/analytics", {})
        self.assertEqual(self.site.analytics_days, [28, 7, 7])

    def test_chat_read_and_reply(self):
        self.site.chats = [{"id": "c1", "visitor_name": "", "guest_key": "guestkey-abc123", "user_id": None, "unread_for_admin": True,
                            "last_message_at": "2026-10-07T16:00:00Z", "last_message_preview": "Hello",
                            "messages": [{"id": "m1", "sender_role": "visitor", "body": "Hello", "created_date": "2026-10-07T16:00:00Z"}]}]
        convs = self.call("/api/chat/list")["conversations"]
        self.assertEqual((convs[0]["id"], convs[0]["unread_for_admin"]), ("c1", True))
        self.assertNotIn("messages", convs[0])
        self.assertEqual([m["body"] for m in self.call("/api/chat/thread", {"id": "c1"})["messages"]], ["Hello"])
        self.assertFalse(self.call("/api/chat/list")["conversations"][0]["unread_for_admin"])
        self.call("/api/chat/reply", {"id": "c1", "body": "   "}, status=400)
        self.assertEqual(self.call("/api/chat/reply", {"id": "c1", "body": " Hi there "})["message"]["body"], "Hi there")
        self.assertEqual(len(self.site.chats[0]["messages"]), 2)

    def test_config_validation(self):
        self.assertEqual(self.call("/api/config", {"pdf_shrink": "strong", "default_price": "7.5"})["config"]["pdf_shrink"], "strong")
        self.assertEqual(storage.load_config()["default_price"], 7.5)
        self.call("/api/config", {"pdf_shrink": "max"}, status=400)
        self.call("/api/config", {"pdf_shrink": "safe"})
        self.assertNotIn("shared_variant_id", self.call("/api/config", {"shared_variant_id": "1"})["config"])
        self.call("/api/config", {"default_price": "0"}, status=400)
        self.call("/api/open", {"url": "file:///etc/passwd"}, status=400)
        self.call("/api/pods/add", {"urls": ""}, status=400)
        self.assertEqual(requests.get(self.url + "../storage.py", timeout=10).status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
