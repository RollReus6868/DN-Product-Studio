"""Open the app window (pywebview) on top of the local server."""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

import server
from app_info import APP_NAME


def _browser_mode(url: str) -> None:
    """No usable native web view (very old Windows without WebView2): use the default browser.
    The page shows a "Thoát" button that calls /api/quit."""
    done = threading.Event()
    server.ROUTES["/api/quit"] = lambda _b: (done.set(), {})[1]
    webbrowser.open(url)
    done.wait()
    time.sleep(0.3)


def main() -> None:
    if os.environ.get("DNPS_SELFCHECK"):
        import selfcheck

        sys.exit(selfcheck.run())
    _srv, url = server.start()
    try:
        import webview

        win = webview.create_window(APP_NAME, url, width=1200, height=800, min_size=(900, 620))
        server.window = win
        server.on_quit = win.destroy
        # Windows: only the Edge WebView2 engine can draw this UI (the old IE engine cannot)
        webview.start(gui="edgechromium" if os.name == "nt" else None)
    except Exception:  # noqa: BLE001 - any web view failure falls back to the browser
        server.window = None
        _browser_mode(url)


if __name__ == "__main__":
    main()
