"""Built-app self check, used by CI on every OS.

Enabled with env DNPS_SELFCHECK=<report.json>. Exercises the real code paths of
the packaged app (UI files, PDF reading, cover conversion, keyring, HTTPS
certificates, and the real window unless DNPS_SELFCHECK_NO_WINDOW=1), writes a
JSON report and returns exit code 0 (report["ok"] tells pass/fail).
"""
from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import threading
import traceback
import urllib.request
from pathlib import Path


def tiny_pdf(text: str = "DN Product Studio self check") -> bytes:
    """A minimal one-page PDF with real text (no extra library needed)."""
    stream = f"BT /F1 18 Tf 40 100 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def _window_check(url: str, report: dict) -> None:
    import webview

    win = webview.create_window("selfcheck", url, width=1200, height=800)

    def loaded():
        try:
            import time

            for _ in range(40):   # the page fills itself after its first API call
                report["nav_items"] = win.evaluate_js("document.querySelectorAll('[data-nav]').length")
                if report["nav_items"]:
                    break
                time.sleep(0.25)
            report["window_title"] = win.evaluate_js("document.title")
            if not report["nav_items"]:
                report["errors"].append("window opened but the UI did not render")
        except Exception:  # noqa: BLE001
            report["errors"].append("window js: " + traceback.format_exc()[-400:])
        finally:
            win.destroy()

    win.events.loaded += lambda: threading.Thread(target=loaded, daemon=True).start()
    webview.start(gui="edgechromium" if os.name == "nt" else None)


def run() -> int:
    path = os.environ["DNPS_SELFCHECK"]
    report: dict = {"ok": False, "errors": []}

    def flush():
        report["ok"] = not report["errors"]
        Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def watchdog():
        report["errors"].append("self-check timed out (window never finished loading)")
        flush()
        os._exit(0)

    timer = threading.Timer(120, watchdog)
    timer.daemon = True
    timer.start()
    try:
        import pdfread
        import prompts
        import scan
        import server
        import updater
        import webstore
        from app_info import APP_VERSION

        report.update(version=APP_VERSION, platform=sys.platform, machine=platform.machine(),
                      frozen=bool(getattr(sys, "frozen", False)), kind=updater.install_kind())
        if sys.platform == "darwin":
            report["mac_arch"] = updater.mac_arch()

        # UI files are bundled and served
        _srv, url = server.start()
        for name in ("", "app.css", "app.js"):
            with urllib.request.urlopen(url + name, timeout=10) as r:
                if r.status != 200 or not r.read():
                    report["errors"].append(f"ui file not served: {name or 'index.html'}")
        report["ui"] = True

        # scan -> read PDF -> prompt -> parse -> cover conversion
        with tempfile.TemporaryDirectory() as td:
            from PIL import Image

            (Path(td) / "Sample-Book.pdf").write_bytes(tiny_pdf())
            Image.new("RGB", (1200, 1700), "#8a6420").save(Path(td) / "Sample-Book.png")
            found = scan.scan_folder(td)
            eb = found["ebooks"][0]
            pdf = pdfread.read_pdf(eb["pdf"])
            report["pdf_pages"], report["pdf_text"] = pdf["pages"], "self check" in pdf["head"]
            if not (eb["cover"] and report["pdf_text"]):
                report["errors"].append("scan / pdf text extraction failed")
            prompt = prompts.ebook_prompt(eb["title"], 9.99, pdf)
            listing = prompts.parse_reply(json.dumps({
                "subtitle": "s", "description": "<p>d</p>", "what_you_learn": ["a"], "who_for": "<ul><li>x</li></ul>",
                "faq": [{"question": "q", "answer": "a"}], "seo_title": "t", "meta_description": "m"}), "ebook")
            report["prompt_chars"] = len(prompt)
            jpeg = webstore.cover_jpeg(eb["cover"])
            report["cover_bytes"] = len(jpeg)
            if not (listing["description"] and jpeg[:2] == b"\xff\xd8"):
                report["errors"].append("listing parse / cover conversion failed")

        try:
            import keyring

            report["keyring"] = type(keyring.get_keyring()).__module__ + "." + type(keyring.get_keyring()).__name__
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"keyring: {exc}")
        try:
            import certifi

            report["certifi"] = Path(certifi.where()).is_file()
            if not report["certifi"]:
                report["errors"].append("certifi bundle missing")
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"certifi: {exc}")

        if os.environ.get("DNPS_SELFCHECK_NO_WINDOW"):
            report["window"] = "skipped"
        else:
            _window_check(url, report)
            report["window"] = "opened"
    except Exception:  # noqa: BLE001
        report["errors"].append(traceback.format_exc())
    timer.cancel()
    flush()
    return 0
