# -*- mode: python ; coding: utf-8 -*-
# Build modes (env DNPS_BUILD_MODE):
#   onedir  (default) Windows: dist/DNProductStudio/ (packed by Inno Setup)
#                     macOS:   dist/DNProductStudio.app
#   onefile           Windows portable: dist/DNProductStudio.exe
# Run:  python -m PyInstaller --noconfirm --clean DNProductStudio.spec
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

sys.path.insert(0, SPECPATH)
from app_info import APP_ID, APP_NAME, APP_VERSION  # noqa: E402

MODE = os.environ.get("DNPS_BUILD_MODE", "onedir").strip().lower()
if MODE not in ("onedir", "onefile"):
    raise SystemExit(f"DNPS_BUILD_MODE must be onedir or onefile, got {MODE!r}")
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

# the whole UI (html, css, js, icon set, fonts) is plain data read at runtime
datas = [("ui", "ui"), ("assets/app.png", "assets"), ("assets/app.ico", "assets")]
# requests needs certifi's CA bundle for HTTPS
datas += collect_data_files("certifi")

hiddenimports = collect_submodules("keyring.backends") + [
    "main", "server", "storage", "scan", "pdfread", "prompts", "spring", "webstore",
    "updater", "app_info", "selfcheck",
]
if IS_WIN:
    hiddenimports += ["win32ctypes.core", "win32ctypes.pywin32.win32cred"]

a = Analysis(
    ["launcher.py"],
    pathex=[SPECPATH],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "numpy", "pandas", "matplotlib", "scipy", "PyQt5", "PyQt6", "PySide2", "PySide6",
              "gi", "qtpy", "cefpython3", "kivy"],
    noarchive=False,
)
pyz = PYZ(a.pure)

version_file = None
if IS_WIN:
    parts = [int(x) for x in (APP_VERSION.split(".") + ["0", "0", "0"])[:3]] + [0]
    tup = ", ".join(map(str, parts))
    version_file = os.path.join(workpath, "version_info.txt")
    os.makedirs(workpath, exist_ok=True)
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{APP_NAME}'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{APP_VERSION}'),
      StringStruct('InternalName', '{APP_ID}'),
      StringStruct('OriginalFilename', '{APP_ID}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{APP_VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""")

icon = "assets/app.icns" if IS_MAC else "assets/app.ico"

if MODE == "onefile":
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name=APP_ID, debug=False, strip=False, upx=False, runtime_tmpdir=None,
        console=False, icon=icon, version=version_file,
    )
else:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name=APP_ID, debug=False, strip=False, upx=False,
        console=False, icon=icon, version=version_file,
        argv_emulation=False,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name=APP_ID, strip=False, upx=False)
    if IS_MAC:
        app = BUNDLE(
            coll,
            name=f"{APP_ID}.app",
            icon=icon,
            bundle_identifier="io.github.dnproductstudio",
            version=APP_VERSION,
            info_plist={
                "CFBundleName": APP_NAME,
                "CFBundleDisplayName": APP_NAME,
                "CFBundleShortVersionString": APP_VERSION,
                "CFBundleVersion": APP_VERSION,
                "NSHighResolutionCapable": True,
                "LSMinimumSystemVersion": "13.0",
                "NSRequiresAquaSystemAppearance": False,
                # the window loads the UI from the app's own server on 127.0.0.1 (plain http)
                "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True, "NSAllowsArbitraryLoads": True},
            },
        )
