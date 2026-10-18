# -*- coding: utf-8 -*-
"""静态资源定位（开发环境与 PyInstaller 打包后均可用）。"""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """应用根目录：打包后指向 PyInstaller 的临时解包目录。"""
    if getattr(sys, "frozen", False):  # pragma: no cover
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    """assets 目录（截图、二维码等）。"""
    return app_root() / "assets"


def icons_dir() -> Path:
    """界面矢量图标目录（assets/icons/*.svg）。"""
    return assets_dir() / "icons"


def icon_path() -> Path:
    """应用图标（窗口/任务栏/打包后的 exe 均使用）。"""
    return assets_dir() / "icon.ico"


def fonts_dir() -> Path:
    """内置字体目录（assets/fonts/*.ttf，如 MiSans 字重）。"""
    return assets_dir() / "fonts"


def styles_dir() -> Path:
    """样式表目录。"""
    return Path(__file__).resolve().parent / "ui" / "styles"
