# -*- coding: utf-8 -*-
"""全局常量：应用元信息、目录路径、组件分类与平台标识。"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Dict, List


# ---------------------------------------------------------------------------
# 全局常量与工具函数
# ---------------------------------------------------------------------------
APP_NAME = "MuRig - 编程开发环境自动装配小工具"


APP_VERSION = "v1.2.3"


# 本项目仓库地址（检查更新、关于我们共用）
REPO_URL = "https://github.com/walnut233/murig"


# 最新版发布页（供用户跳转下载）
RELEASES_LATEST_URL = f"{REPO_URL}/releases/latest"


# GitHub 最新 Release 接口：返回 tag_name / html_url / body / published_at
# （未认证请求限流很严，60 次/小时/IP，失败时回退到下面的订阅源）
RELEASES_API = "https://api.github.com/repos/walnut233/murig/releases/latest"


# Releases 订阅源：不受上面那条接口的限流约束，作为兜底来源
RELEASES_ATOM = f"{REPO_URL}/releases.atom"


CONFIG_DIR = Path.home() / ".env-tools"


CONFIG_FILE = CONFIG_DIR / "config.json"


# 应用设置目录：固定在家目录下，不随工作空间移动（工作空间可被用户改到任意盘）
SETTINGS_DIR = Path.home() / ".murig"


SETTINGS_FILE = SETTINGS_DIR / "config.json"


# ---------------------------------------------------------------------------
# 组件分类
# ---------------------------------------------------------------------------
# key -> 分类显示名；"all" 只用于筛选栏
CATEGORIES: Dict[str, str] = {
    "all": "全部",
    "java": "Java 相关",
    "python": "Python 相关",
    "frontend": "前端相关",
    "database": "数据库",
    "bigdata": "大数据",
    "ai": "AI 相关",
}


# 卡片排列顺序（不含 "all"）
CATEGORY_ORDER: List[str] = ["java", "python", "frontend", "database", "bigdata", "ai"]


# 当前操作系统标识：'Windows' / 'Darwin' / 'Linux'
CURRENT_OS = platform.system()


# 当前 CPU 架构（大致判断，用于挑选二进制包）
MACHINE = platform.machine().lower()


IS_ARM = ("arm" in MACHINE) or ("aarch64" in MACHINE)
