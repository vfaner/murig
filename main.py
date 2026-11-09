# -*- coding: utf-8 -*-
"""MuRig 启动入口。

所有实现已按职责拆到 murig 包：
    murig.core     平台能力（常量 / 环境变量 / 解包 / 工作空间 / 后台线程）
    murig.catalog  组件清单与版本抓取
    murig.ui       界面层（主题 / 控件 / 对话框 / 主窗口）

用法：
    python main.py
"""

from __future__ import annotations

import sys

from murig.app import main

if __name__ == "__main__":
    sys.exit(main())
