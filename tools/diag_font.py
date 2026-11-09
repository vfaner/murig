# -*- coding: utf-8 -*-
"""字体 / DPI 渲染环境诊断（不打开窗口，仅打印环境信息）。

用法：
    python tools/diag_font.py                 # 默认 directwrite
    set MURIG_FONT_ENGINE=gdi && python tools/diag_font.py   # 对比 GDI 引擎
    set MURIG_FONT_ENGINE=freetype && python tools/diag_font.py

关注点：
- Platform 应为 windows；Font engine 为预期引擎（directwrite 最平滑）
- devicePixelRatio 与系统缩放一致（125% -> 1.25）
- FontInfo.family 应解析到 Microsoft YaHei UI（exactMatch=True）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import murig.app  # noqa: F401  触发字体引擎 / 高 DPI 环境变量设置（必须早于 QApplication）

from PySide6.QtGui import QFontInfo, QGuiApplication  # noqa: E402


def main() -> int:
    app = QGuiApplication(sys.argv)
    font = murig.app._default_font()
    if font is not None:
        app.setFont(font)

    screen = QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else float("nan")
    logical = screen.logicalDotsPerInch() if screen else float("nan")
    physical = screen.physicalDotsPerInchX() if screen else float("nan")

    info = QFontInfo(app.font())

    print("=== MuRig 字体 / DPI 诊断 ===")
    print(f"Platform            : {QGuiApplication.platformName()}")
    print(f"QT_QPA_PLATFORM     : {os.environ.get('QT_QPA_PLATFORM', '(未设置)')}")
    print(f"MURIG_FONT_ENGINE   : {os.environ.get('MURIG_FONT_ENGINE', '(默认)')}")
    print(f"QT_ENABLE_HIGHDPI   : {os.environ.get('QT_ENABLE_HIGHDPI_SCALING', '(未设置)')}")
    print(f"devicePixelRatio    : {dpr}   （系统缩放约 {dpr * 100:.0f}%）")
    print(f"logicalDpi          : {logical:.1f}")
    print(f"physicalDpiX        : {physical:.1f}")
    if screen:
        g = screen.geometry()
        print(f"屏幕分辨率          : {g.width()} x {g.height()}")
    print(f"Font family         : {info.family()}  (exactMatch={info.exactMatch()})")
    print(f"Font pointSize      : {info.pointSize()} pt / {info.pixelSize()} px")
    print(f"Font style/weight   : {info.style()} / {info.weight()}")
    print("")
    print("提示：若仍有锯齿，可尝试 MURIG_FONT_ENGINE=gdi 或 freetype 对比；")
    print("      100% 缩放下 devicePixelRatio 应为 1.0，125% 应为 1.25。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
