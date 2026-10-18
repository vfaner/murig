# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for MuRig.

跨平台构建脚本，在 Windows/macOS/Linux 上分别运行：
    pyinstaller murig.spec

产物路径：
    dist/murig           # Linux 单可执行文件
    dist/murig.exe       # Windows 单可执行文件
    dist/murig.app       # macOS .app bundle
"""
import re
import sys
from pathlib import Path

APP_NAME = "murig"
SPEC_DIR = Path(SPECPATH).resolve() if 'SPECPATH' in globals() else Path.cwd()

# 版本号跟随 murig/core/constants.py 的 APP_VERSION（去掉前缀 v），
# 避免 macOS bundle 里写的版本与界面显示的不一致
_version = re.search(
    r'APP_VERSION\s*=\s*"([^"]+)"',
    (SPEC_DIR / "murig" / "core" / "constants.py").read_text(encoding="utf-8"),
).group(1).lstrip("v")

# 打进包里的静态资源：应用图标 + 界面 SVG 图标 + QSS 主题。
# 截图（murig*.png）只有 README 用，运行时不读，不进包
datas = [
    (str(SPEC_DIR / "assets" / "icons"), "assets/icons"),
    (str(SPEC_DIR / "assets" / "icon.ico"), "assets"),
    # 内置界面字体（MiSans 两个字重），缺失时自动回退系统字体
    (str(SPEC_DIR / "assets" / "fonts"), "assets/fonts"),
    (str(SPEC_DIR / "murig" / "ui" / "styles"), "murig/ui/styles"),
]

# 应用图标：Windows 需要 .ico；macOS 的 .app 需要 .icns（缺失则沿用默认图标）
icon_file = SPEC_DIR / "assets" / "icon.ico"
exe_icon = str(icon_file) if icon_file.exists() and sys.platform == "win32" else None
icns_file = SPEC_DIR / "assets" / "icon.icns"
bundle_icon = str(icns_file) if icns_file.exists() else None

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
# 剔除用不到的 Qt 二进制 / 翻译
# ---------------------------------------------------------------------------
# excludes 只能挡 Python 模块导入，PyInstaller 的 Qt hook 仍会按依赖把一批
# 本应用用不到的 DLL / 插件 / 翻译收进包（Qml/Quick 全家桶、软件 OpenGL 兜底
# opengl32sw、Pdf、Network、VirtualKeyboard、多语言 qm 等），这里按名字剔除。
# 注意保留 Qt6Svg / QtSvg：卡片图标的 QSvgRenderer 需要它；
# 保留 libssl/libcrypto：stdlib ssl（requests 下载）需要。
import re

_BIN_DROP = re.compile(
    r"(?i)("
    r"opengl32sw"                      # 软件渲染 OpenGL 兜底，19.7MB
    r"|qt6quick|qt6qml|qt6pdf"         # QML/Quick 全家桶、Pdf 预览
    r"|qt6opengl|qt6network"           # OpenGL、Qt 网络（下载走 requests）
    r"|qt6virtualkeyboard|qt6designer|qt6shadertools|qt6uitools"
    r"|qt6webengine|qt6multimedia|qt6avcodec|qt6mediatools"
    r"|qt6location|qt6positioning|qt6sensors|qt6serialport"
    r"|qt6bluetooth|qt6nfc|qt6websockets|qt6webchannel"
    r"|qt6texttospeech|qt6remoteobjects|qt6scxml|qt6statemachine"
    r"|qt6test|qt6help|qt6charts|qt6datavis|qt63d"
    r"|[\\/]qml[\\/]"                  # QML 导入目录
    r"|[\\/]translations[\\/]"         # Qt 自带的多语言翻译（全中文硬编码）
    r")",
)
a.binaries = [e for e in a.binaries if not _BIN_DROP.search(e[0])]
a.datas = [e for e in a.datas if not _BIN_DROP.search(e[0])]

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
    icon=exe_icon,
)

# ---------------------------------------------------------------------------
# macOS .app bundle
# ---------------------------------------------------------------------------
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name=f"{APP_NAME}.app",
        icon=bundle_icon,
        bundle_identifier="com.qqmu.murig",
        info_plist={
            "CFBundleName": "MuRig",
            "CFBundleDisplayName": "MuRig - 编程开发环境自动装配小工具",
            "CFBundleShortVersionString": _version,
            "CFBundleVersion": _version,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "10.13.0",
        },
    )
