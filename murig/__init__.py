# -*- coding: utf-8 -*-
"""MuRig · 编程开发环境自动装配小工具。

包结构：
    murig.core      平台能力层（常量 / 环境变量 / 解包 / 工作空间 / 线程）
    murig.catalog   组件清单与版本抓取
    murig.ui        PySide6 界面层（主题 / 控件 / 对话框 / 主窗口）
    murig.app       应用入口
"""

from __future__ import annotations

from .core.constants import APP_NAME, APP_VERSION

__all__ = ["APP_NAME", "APP_VERSION", "main"]


def main() -> int:  # 便捷入口：python -c "import murig; murig.main()"
    from .app import main as _main

    return _main()
