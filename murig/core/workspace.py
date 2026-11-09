# -*- coding: utf-8 -*-
"""三级工作空间解析：组件覆盖 > 分类 > 全局 > 默认目录。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .constants import CONFIG_DIR, CONFIG_FILE, SETTINGS_DIR, SETTINGS_FILE
from .utils import ensure_dir


class WorkspaceManager:
    """三级工作空间解析：组件覆盖 > 分类工作空间 > 全局默认 > 内置 CONFIG_DIR。

    设置存于 SETTINGS_FILE（~/.murig/config.json 的 "workspace" 段），与工作空间
    本身分离：把工作空间改到别的盘不会丢掉配置。旧版设置文件 CONFIG_FILE
    （~/.env-tools/config.json）在首次加载时整体迁移过来。
    """

    def __init__(self) -> None:
        self.global_ws: Optional[str] = None
        self.categories: Dict[str, str] = {}
        self.components: Dict[str, str] = {}
        self.migrated = False

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> "WorkspaceManager":
        """读取设置；必要时从旧 CONFIG_FILE 一次性迁移。"""
        mgr = cls()
        data: Dict = {}
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        elif CONFIG_FILE.exists():
            # 旧版（v1.1.x 及以前）设置在工作空间内：整体搬到新位置
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            mgr._apply(data.get("workspace", {}))
            mgr.migrated = True
            mgr.save(data.get("selections", {}))
            return mgr
        mgr._apply(data.get("workspace", {}))
        return mgr

    def _apply(self, ws: Dict) -> None:
        self.global_ws = ws.get("global") or None
        self.categories = dict(ws.get("categories") or {})
        self.components = dict(ws.get("components") or {})

    # ------------------------------------------------------------------
    def save(self, selections: Optional[Dict] = None) -> None:
        """落盘 workspace 段；selections 由调用方并入（保持单文件单 schema）。"""
        try:
            ensure_dir(SETTINGS_DIR)
            data: Dict = {}
            if SETTINGS_FILE.exists():
                try:
                    data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data["workspace"] = {
                "global": self.global_ws,
                "categories": self.categories,
                "components": self.components,
            }
            if selections is not None:
                data["selections"] = selections
            SETTINGS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    def resolve(self, key: str, category: str) -> Path:
        """组件安装根目录：组件覆盖 > 分类 > 全局 > CONFIG_DIR。"""
        raw = self.components.get(key) or self.categories.get(category) or self.global_ws
        return Path(raw) if raw else CONFIG_DIR

    def roots_for(self, key: str, category: str) -> List[Path]:
        """本地扫描用的根目录列表：当前解析根 + 默认根（去重），保证换工作空间
        后旧位置已解压的组件仍能被看见、被配置。"""
        roots = [self.resolve(key, category)]
        if CONFIG_DIR not in roots:
            roots.append(CONFIG_DIR)
        return roots

    # ------------------------------------------------------------------
    def set_global(self, path: Optional[str]) -> None:
        self.global_ws = path or None
        self.save()

    def set_category(self, category: str, path: Optional[str]) -> None:
        if path:
            self.categories[category] = path
        else:
            self.categories.pop(category, None)
        self.save()

    def set_component(self, key: str, path: Optional[str]) -> None:
        if path:
            self.components[key] = path
        else:
            self.components.pop(key, None)
        self.save()

    # ------------------------------------------------------------------
    def download_cache_files(self) -> List[Path]:
        """收集所有工作空间下组件 downloads 目录里的安装包（清理用）。

        覆盖全局 / 分类 / 组件覆盖 / 内置默认四类根，去重后逐根扫描
        `<root>/<组件>/downloads/<文件>`。
        """
        roots: List[Path] = [CONFIG_DIR]
        if self.global_ws:
            roots.append(Path(self.global_ws))
        roots.extend(Path(p) for p in self.categories.values() if p)
        roots.extend(Path(p) for p in self.components.values() if p)

        files: List[Path] = []
        seen: set = set()
        for root in roots:
            try:
                rp = root.resolve()
            except OSError:
                continue
            if rp in seen or not root.exists():
                seen.add(rp)
                continue
            seen.add(rp)
            for dl_dir in root.glob("*/downloads"):
                if dl_dir.is_dir():
                    for f in dl_dir.iterdir():
                        if f.is_file():
                            files.append(f)
        return files


# 全局单例：启动时加载一次，UI 修改后即时 save
WS = WorkspaceManager.load()
