# -*- coding: utf-8 -*-
"""平台能力层：常量、工具、环境变量、解包、工作空间、后台线程。"""

from __future__ import annotations

from .constants import (
    APP_NAME, APP_VERSION, CATEGORIES, CATEGORY_ORDER, CONFIG_DIR, CONFIG_FILE,
    CURRENT_OS, IS_ARM, MACHINE, SETTINGS_DIR, SETTINGS_FILE,
)
from .env import EnvManager
from .models import Component, ComponentVersion, DetectResult
from .utils import ensure_dir, human_size
from .workspace import WS, WorkspaceManager

__all__ = [
    "APP_NAME", "APP_VERSION", "CATEGORIES", "CATEGORY_ORDER", "CONFIG_DIR",
    "CONFIG_FILE", "CURRENT_OS", "IS_ARM", "MACHINE", "SETTINGS_DIR",
    "SETTINGS_FILE", "EnvManager", "Component", "ComponentVersion",
    "DetectResult", "ensure_dir", "human_size", "WS", "WorkspaceManager",
]
