# -*- coding: utf-8 -*-
"""界面图标。

图标来源：
1. assets/icons/*.svg —— 统一的实心图标包（信息 / 刷新 / 设置 / 文件夹），
   填充色按调用处传入的颜色注入（SVG 本身不带 fill，默认纯黑）；
2. 窗口控制按钮（最小化 / 最大化 / 还原 / 关闭）——图标包里没有对应图形，
   仍用 QPainter 线性描边绘制，保证这一组三个按钮的视觉重量一致。

渲染均做 2x 超采样，高分屏不糊。
"""

from __future__ import annotations

import re
from typing import Callable

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtSvg import QSvgRenderer

from ..resources import icons_dir

# 标题栏（深色底）上的默认图标色
BAR_FG = "#e6eaf3"
# 卡片 / 浅色底上的默认图标色
BODY_FG = "#4f46e5"

# SVG 渲染结果缓存：(文件名, 尺寸, 颜色) -> QIcon
_SVG_CACHE: dict[tuple[str, int, str], QIcon] = {}


def _icon(size: int, color: str, draw: Callable[[QPainter], None]) -> QIcon:
    """在 24x24 逻辑坐标系里绘制并缩放到 size 像素（2x 超采样）。"""
    dpr = 2.0
    px = max(1, int(size * dpr))
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(2.0)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(QBrush())  # NoBrush：仅描边不填充
    scale = px / 24.0
    p.scale(scale, scale)
    draw(p)
    p.end()
    pm.setDevicePixelRatio(px / size)
    return QIcon(pm)


def _polyline(p: QPainter, *pts: tuple[float, float]) -> None:
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(QPointF(x, y))
    p.drawPath(path)


# --------------------------------------------------------------------------
# 具体图标
# --------------------------------------------------------------------------
def _svg_icon(name: str, size: int, color: str) -> QIcon:
    """渲染 assets/icons/<name>.svg，并注入填充色。

    SVG 只有一条 path 且不带 fill（默认纯黑），这里把颜色写进去再渲染。
    """
    key = (name, size, color)
    cached = _SVG_CACHE.get(key)
    if cached is not None:
        return cached

    text = (icons_dir() / f"{name}.svg").read_text(encoding="utf-8")
    if 'fill="' in text:
        text = re.sub(r'fill="[^"]*"', f'fill="{color}"', text)
    else:
        text = text.replace("<path", f'<path fill="{color}"')

    dpr = 2.0
    px = max(1, int(size * dpr))
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    renderer = QSvgRenderer(QByteArray(text.encode("utf-8")))
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    pm.setDevicePixelRatio(px / size)
    icon = QIcon(pm)
    _SVG_CACHE[key] = icon
    return icon


def about_icon(size: int = 16, color: str = BAR_FG) -> QIcon:
    """信息圆圈（关于）。"""
    return _svg_icon("info-circle", size, color)


def refresh_icon(size: int = 16, color: str = BAR_FG) -> QIcon:
    """循环箭头（刷新版本）。"""
    return _svg_icon("reload", size, color)


def folder_icon(size: int = 16, color: str = BODY_FG) -> QIcon:
    """文件夹（卡片目录按钮、标题栏打开目录按钮）。"""
    return _svg_icon("folder", size, color)


def settings_icon(size: int = 14, color: str = BAR_FG) -> QIcon:
    """齿轮（设置）。"""
    return _svg_icon("setting", size, color)


def minimize_icon(size: int = 14, color: str = BAR_FG) -> QIcon:
    def draw(p: QPainter) -> None:
        _polyline(p, (5, 12), (19, 12))
    return _icon(size, color, draw)


def maximize_icon(size: int = 14, color: str = BAR_FG) -> QIcon:
    def draw(p: QPainter) -> None:
        p.drawRoundedRect(QRectF(5.5, 5.5, 13, 13), 2, 2)
    return _icon(size, color, draw)


def restore_icon(size: int = 14, color: str = BAR_FG) -> QIcon:
    def draw(p: QPainter) -> None:
        _polyline(p, (9, 6.5), (17.5, 6.5), (17.5, 15))
        p.drawRoundedRect(QRectF(6.5, 9, 8.5, 8.5), 2, 2)
    return _icon(size, color, draw)


def close_icon(size: int = 14, color: str = BAR_FG) -> QIcon:
    def draw(p: QPainter) -> None:
        _polyline(p, (6.5, 6.5), (17.5, 17.5))
        _polyline(p, (17.5, 6.5), (6.5, 17.5))
    return _icon(size, color, draw)
