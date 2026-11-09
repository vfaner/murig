# -*- coding: utf-8 -*-
"""通用安装行为设置。

两个安装行为开关：是否在安装完成后自动写入环境变量（写入 XXX_HOME / PATH
会改动用户配置，默认关闭，需要时再手动点「配置环境变量」或打开开关），
以及安装完成后是否自动清理下载的安装包。

设置落在 SETTINGS_FILE 的 "install" 段，与工作空间、下载设置同一文件。
"""

from __future__ import annotations

import json
import os
from typing import Dict

from .constants import SETTINGS_DIR, SETTINGS_FILE
from .utils import ensure_dir


class InstallSettings:
    """安装行为设置。"""

    def __init__(self) -> None:
        # 安装完成后自动配置环境变量；关闭时仅解压，配置留给用户决定
        self.auto_env: bool = False
        # 安装成功后自动清理下载的安装包；关闭时保留，便于重装 / 离线复用
        self.auto_clean: bool = True

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> "InstallSettings":
        s = cls()
        try:
            if SETTINGS_FILE.exists():
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                d = data.get("install") or {}
                s.auto_env = bool(d.get("auto_env"))
                # 缺省为 True：老版本一直是安装后自动清理
                s.auto_clean = bool(d.get("auto_clean", True))
        except Exception:
            pass
        # 环境变量方便临时对比：MURIG_AUTO_ENV=1 打开
        env = os.environ.get("MURIG_AUTO_ENV")
        if env:
            s.auto_env = env.strip().lower() in ("1", "true", "yes", "on")
        # MURIG_AUTO_CLEAN=0 关闭自动清理
        env_clean = os.environ.get("MURIG_AUTO_CLEAN")
        if env_clean:
            s.auto_clean = env_clean.strip().lower() in ("1", "true", "yes", "on")
        return s

    def save(self) -> None:
        try:
            ensure_dir(SETTINGS_DIR)
            data: Dict = {}
            if SETTINGS_FILE.exists():
                try:
                    data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data["install"] = {
                "auto_env": self.auto_env,
                "auto_clean": self.auto_clean,
            }
            SETTINGS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


# 全局单例：启动时加载一次，UI 修改后即时 save
INSTALL = InstallSettings.load()


class UISettings:
    """界面外观设置。

    目前只有一个开关：是否使用系统字体。默认否 —— 统一使用内置 MiSans
    渲染，避免不同系统字体差异导致版式跳动；用户偏好系统字体时可打开，
    切换后立即生效（不需要重启）。

    设置落在 SETTINGS_FILE 的 "ui" 段。
    """

    def __init__(self) -> None:
        # True = 用系统字体；False = 用内置 MiSans
        self.system_font: bool = False

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> "UISettings":
        s = cls()
        try:
            if SETTINGS_FILE.exists():
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                d = data.get("ui") or {}
                s.system_font = bool(d.get("system_font"))
        except Exception:
            pass
        # MURIG_SYSTEM_FONT=1 可强制走系统字体，便于对比
        env = os.environ.get("MURIG_SYSTEM_FONT")
        if env:
            s.system_font = env.strip().lower() in ("1", "true", "yes", "on")
        return s

    def save(self) -> None:
        try:
            ensure_dir(SETTINGS_DIR)
            data: Dict = {}
            if SETTINGS_FILE.exists():
                try:
                    data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data["ui"] = {"system_font": self.system_font}
            SETTINGS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


UI = UISettings.load()
