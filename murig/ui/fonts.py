# -*- coding: utf-8 -*-
"""应用字体：默认使用内置 MiSans，可在设置里切换回系统字体。

字体文件放在 assets/fonts/（打包时也一起打进去），包含 MiSans 的两个字重：
Regular（正文）与 Demibold（QSS 里 font-weight 600/700 的标题、按钮）。

为什么不全部字重 / 可变字体：
- 单个中文字重约 7.7MB，多带一个就多打包一份；两个足够覆盖界面用到的
  400 / 600 / 700（700 会自动落到最近的 600）；
- MiSans 的可变字体 VF 是单文件但更大（19MB），且 Qt 对可变字重轴的选取
  在部分平台上仍退回合成加粗，不如静态字重可控。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QWidget

from ..core.constants import CURRENT_OS
from ..resources import fonts_dir

__all__ = ["MISANS_FAMILY", "misans_available", "app_font", "apply_app_font"]


# assets/fonts 下的字体文件（全部加载，Qt 按 family + weight 匹配）
_FONT_FILES = ("MiSans-Regular.ttf", "MiSans-Demibold.ttf")

# 加载后注册的字体家族名（不同字重共用同一个 family，靠 weight 区分）
MISANS_FAMILY = "MiSans"

_loaded = False
_family_ok = False


def _load_misans() -> bool:
    """把内置字重注册到 Qt 字体库（只做一次）。返回是否注册成功。"""
    global _loaded, _family_ok
    if _loaded:
        return _family_ok
    if QGuiApplication.instance() is None:
        # Qt 字体库必须在 Q(Gui)Application 之后才能用，否则会直接崩
        return False
    _loaded = True
    d = fonts_dir()
    for name in _FONT_FILES:
        path = d / name
        if not path.exists():
            continue
        if QFontDatabase.addApplicationFont(str(path)) >= 0:
            _family_ok = True
    if _family_ok:
        families = QFontDatabase.families()
        _family_ok = MISANS_FAMILY in families
    return _family_ok


def misans_available() -> bool:
    """内置 MiSans 是否可用（文件缺失则自动回系统字体）。"""
    return _load_misans()


def _point_size(use_system: bool) -> int:
    """各平台的基础字号：macOS 点值与 Windows/Linux 换算不同。"""
    if CURRENT_OS == "Darwin":
        return 13
    return 10


def app_font(use_system: bool) -> Optional[QFont]:
    """返回应用字体；use_system 为 True 时用平台默认，否则用内置 MiSans。

    返回 None 表示"不设置，交给 Qt 默认"，Linux 下即 Qt 自己挑的默认字体。
    """
    size = _point_size(use_system)

    if not use_system:
        if _load_misans():
            f = QFont(MISANS_FAMILY, size)
        else:  # 字体文件缺失：回退到系统字体，不至于满屏方框
            return app_font(True)
    else:
        f = QFont()
        if CURRENT_OS == "Windows":
            # 雅黑 UI 版字距更松，小字号最清晰
            f.setFamily("Microsoft YaHei UI")
        elif CURRENT_OS == "Darwin":
            f.setFamily("PingFang SC")
        else:
            return None
        f.setPointSize(size)

    # 明确要求抗锯齿与高质量（亚像素）渲染：设置 family/size 不影响这些策略
    f.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
    )
    # 全量 hinting：字模对齐像素网格，小字号中文笔画更实、不发虚
    f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return f


def _set_font_recursive(widget, font: QFont) -> None:
    """把字体下发到该控件及其所有子控件（QSS 会阻断继承，只能逐个设置）。"""
    widget.setFont(font)
    for child in widget.children():
        if isinstance(child, QWidget):
            _set_font_recursive(child, font)


def apply_app_font(app, use_system: bool) -> str:
    """把字体应用到整个应用，返回实际使用的字体家族名（用于界面提示）。

    已存在的控件没有单独设置字体时会跟随 QApplication 的字体变化立即更新。
    """
    if not use_system and not misans_available():
        # 内置字体缺失，静默回系统字体
        use_system = True
    font = app_font(use_system)
    if font is not None:
        app.setFont(font)
        # QSS 给 QWidget 设了 font-size，控件字体在 polish 时就被解析并缓存，
        # 应用级字体变化不会自动向下继承。这里"重新抛光"：清一下样式表再设回，
        # 让所有控件按新字体重新解析 —— 相比逐个 setFont，这样不会覆盖 QSS 里
        # 显式指定的字体（如日志区的等宽字体）。
        qss = app.styleSheet()
        if qss:
            app.setStyleSheet("")
            app.setStyleSheet(qss)
    family = font.family() if font is not None else ""
    if not family:
        family = app.font().family()
    return family
