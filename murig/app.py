# -*- coding: utf-8 -*-
"""应用入口：组装 QApplication + 主题 + 主窗口。"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# 字体 / 高 DPI 渲染设置（必须在 QApplication 创建之前完成）
# ---------------------------------------------------------------------------
# 启用高 DPI 缩放，避免高分屏整体位图拉伸导致模糊
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

# Windows 默认使用 GDI 字体引擎（灰度抗锯齿，小字号中文发毛/锯齿）。
# 强制切到 DirectWrite：支持亚像素抗锯齿 + 更好的字距，字体边缘明显更干净。
# 可用 MURIG_FONT_ENGINE=gdi|directwrite|freetype 覆盖以做对比。
if sys.platform == "win32":
    _engine = os.environ.get("MURIG_FONT_ENGINE", "directwrite").strip()
    os.environ.setdefault("QT_QPA_PLATFORM", f"windows:fontengine={_engine or 'directwrite'}")

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .core.constants import APP_NAME
from .core.settings import UI
from .resources import icon_path
from .ui.fonts import app_font
from .ui.main_window import MainWindow
from .ui.theme import apply_theme


def _default_font():
    """应用字体：默认内置 MiSans，用户在设置里打开则用系统字体。"""
    return app_font(UI.system_font)


def _app_icon() -> QIcon | None:
    """加载 assets/icon.ico；缺失时返回 None（不至于因此启动失败）。"""
    p = icon_path()
    if not p.exists():
        return None
    icon = QIcon(str(p))
    return icon if not icon.isNull() else None


def _set_win_app_id() -> None:
    """Windows 任务栏：声明独立 AppUserModelID。

    不设置的话，任务栏会把本程序归到 python.exe 名下并显示 Python 图标。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.qqmu.murig")
    except Exception:
        pass


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    _set_win_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    icon = _app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    font = _default_font()
    if font is not None:
        app.setFont(font)
    apply_theme(app)
    win = MainWindow()
    if icon is not None:
        win.setWindowIcon(icon)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
