# -*- coding: utf-8 -*-
"""全局 QSS 主题加载。

样式集中在 murig/ui/styles/theme.qss，代码里不再内联大段样式字符串；
控件只负责设置 objectName / property，外观统一由主题表描述。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QApplication

from ..resources import styles_dir

_CACHE: Optional[str] = None


def stylesheet_path() -> Path:
    return styles_dir() / "theme.qss"


def load_stylesheet(force_reload: bool = False) -> str:
    """读取主题文件（带缓存；开发期可 force_reload 热更新）。"""
    global _CACHE
    if _CACHE is None or force_reload:
        path = stylesheet_path()
        _CACHE = path.read_text(encoding="utf-8") if path.exists() else ""
    return _CACHE


def apply_theme(app: QApplication, force_reload: bool = False) -> None:
    """把主题应用到整个应用。"""
    qss = load_stylesheet(force_reload=force_reload)
    if qss:
        app.setStyleSheet(qss)
