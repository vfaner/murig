# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for env-auto-setup.

跨平台构建脚本，在 Windows/macOS/Linux 上分别运行：
    pyinstaller env-auto-setup.spec

产物路径：
    dist/env-auto-setup           # Linux 单可执行文件
    dist/env-auto-setup.exe       # Windows 单可执行文件
    dist/env-auto-setup.app       # macOS .app bundle
"""
import sys
from pathlib import Path

APP_NAME = "env-auto-setup"
SPEC_DIR = Path(SPECPATH).resolve() if 'SPECPATH' in globals() else Path.cwd()

# 打进包里的静态资源（打赏二维码、应用截图等）
datas = [
    (str(SPEC_DIR / "assets"), "assets"),
]

hidden_imports = [
    # PySide6 相关子模块
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    # requests 依赖
    "requests",
    "urllib3",
    "charset_normalizer",
    "certifi",
    "idna",
]

# ---------------------------------------------------------------------------
# 分析
# ---------------------------------------------------------------------------
a = Analysis(
    ['main.py'],
    pathex=[str(SPEC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 不需要的大模块
        "tkinter",
        "test",
        "unittest",
        "PySide6.QtNetwork",
        "PySide6.QtOpenGL",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtSql",
        "PySide6.QtMultimedia",
        "PySide6.Qt3DCore",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# ---------------------------------------------------------------------------
# EXE / 单文件产物
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX 在 mac 上会导致启动崩溃，禁用
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # GUI 应用，不显示黑色控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon=str(SPEC_DIR / "assets" / "icon.icns"),  # 有 icon 时可开启
)

# ---------------------------------------------------------------------------
# macOS .app bundle
# ---------------------------------------------------------------------------
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name=f"{APP_NAME}.app",
        # icon=str(SPEC_DIR / "assets" / "icon.icns"),
        bundle_identifier="com.rgh.env-auto-setup",
        info_plist={
            "CFBundleName": "环境自动装配小工具",
            "CFBundleDisplayName": "环境自动装配小工具",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "10.13.0",
        },
    )
