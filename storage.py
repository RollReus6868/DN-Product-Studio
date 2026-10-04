"""Config, saved product list and the secret token (no GUI imports)."""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from app_info import APP_ID

DEFAULTS = {
    "site_base": os.environ.get("DNPS_SITE_BASE") or "https://base44.app",
    "site_app_id": "6aa80a3918e73ce9a7b4d0f7",
    "site_url": "https://dangerous-scripture-stream-hub.base44.app",
    "default_price": 9.99,
    "shared_variant_id": "",
    "ebook_folder": "",
    "theme": "gold",
    "mode": "dark",
    "sidebar_open": True,
}
_KEYRING_USER = "tool_token"
_lock = threading.RLock()


def app_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin" and not os.environ.get("APPDATA"):
        base = Path.home() / "Library" / "Application Support"
    else:   # Linux, and tests / CI that point APPDATA at a temp folder
        base = Path(os.environ.get("APPDATA") or Path.home() / ".config")
    d = base / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(name: str, default):
    try:
        return json.loads((app_dir() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(name: str, data) -> None:
    path = app_dir() / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def load_config() -> dict:
    with _lock:
        saved = _read("config.json", {})
        return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def save_config(changes: dict) -> dict:
    with _lock:
        cfg = load_config()
        cfg.update({k: v for k, v in changes.items() if k in DEFAULTS})
        _write("config.json", cfg)
        return cfg


def load_items() -> dict:
    """{"ebook": {id: item}, "pod": {id: item}} — everything the user has prepared so far."""
    with _lock:
        data = _read("items.json", {})
        return {"ebook": dict(data.get("ebook") or {}), "pod": dict(data.get("pod") or {})}


def save_items(items: dict) -> None:
    with _lock:
        _write("items.json", items)


# ------------------------------------------------------------------ secret token
def get_token() -> str:
    env = os.environ.get("DNPS_TOOL_TOKEN")
    if env:
        return env
    try:
        import keyring

        return keyring.get_password(APP_ID, _KEYRING_USER) or ""
    except Exception:  # noqa: BLE001 - no keyring backend: behave as "not set"
        return ""


def set_token(token: str) -> None:
    import keyring

    keyring.set_password(APP_ID, _KEYRING_USER, token.strip())
