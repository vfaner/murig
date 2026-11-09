# -*- coding: utf-8 -*-
"""与 UI 无关的通用小工具。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .constants import CURRENT_OS


def human_size(num: float) -> str:
    """把字节数转换为可读字符串。"""
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def reveal_file(path) -> bool:
    """在文件管理器中定位到该文件（打开它所在的目录并选中）。

    Windows 用 explorer /select,、macOS 用 open -R；Linux 没有统一的选中
    协议，退化为打开所在目录。失败时也再退一次到「打开目录」。
    """
    p = Path(path)
    directory = p if p.is_dir() else p.parent
    try:
        if CURRENT_OS == "Windows" and p.is_file():
            subprocess.Popen(["explorer", f"/select,{str(p)}"])
            return True
        if CURRENT_OS == "Darwin" and p.is_file():
            subprocess.Popen(["open", "-R", str(p)])
            return True
    except Exception:
        pass
    return open_in_file_manager(directory)


def ensure_dir(path: Path) -> None:
    """确保目录存在。"""
    path.mkdir(parents=True, exist_ok=True)


def open_in_file_manager(path) -> bool:
    """用系统文件管理器打开目录（资源管理器 / Finder / 桌面文件管理器）。

    目录不存在时先创建（工作空间可能还没装过任何东西）。
    非阻塞启动，成功返回 True。
    """
    p = Path(path)
    try:
        ensure_dir(p)
    except Exception:
        return False
    try:
        if CURRENT_OS == "Windows":
            subprocess.Popen(["explorer", str(p)])
        elif CURRENT_OS == "Darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return True
    except Exception:
        return False
