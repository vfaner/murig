# -*- coding: utf-8 -*-
"""版本列表缓存：网络受限（GitHub 限流、代理/加速器拦截、断网）时的兜底。

抓取成功即落盘；抓取失败时回退到最近一次成功的结果（不限 TTL），
避免共享出口 IP 打满 GitHub 匿名配额后组件直接没有版本可选。

缓存位置：CONFIG_DIR/version_cache/<key>.json，只写不主动清理（体积很小）。
"""

from __future__ import annotations

import json as _json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable, List, Optional

from ..core.constants import CONFIG_DIR
from ..core.models import ComponentVersion

CACHE_DIR = CONFIG_DIR / "version_cache"
# 缓存“新鲜期”：过期后仍会被使用，只是提示信息不同
FRESH_TTL = 6 * 3600


def cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _age_text(saved_at: int) -> str:
    delta = max(0, int(time.time()) - saved_at)
    if delta < 60:
        return f"{delta} 秒"
    if delta < 3600:
        return f"{delta // 60} 分钟"
    if delta < 86400:
        return f"{delta // 3600} 小时"
    return f"{delta // 86400} 天"


def load_cached(key: str) -> tuple[Optional[List[ComponentVersion]], str]:
    """读取缓存，返回 (版本列表, 描述文案)。无缓存时列表为 None。"""
    path = cache_path(key)
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
        versions = [ComponentVersion(**item) for item in data.get("versions", [])]
        if not versions:
            return None, ""
        return versions, _age_text(int(data.get("saved_at", 0)))
    except Exception:
        return None, ""


def save_cached(key: str, versions: List[ComponentVersion]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path(key).write_text(
            _json.dumps(
                {"saved_at": int(time.time()), "versions": [asdict(v) for v in versions]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass  # 缓存写失败不影响主流程


def cached_versions(key: str,
                    loader: Callable[[], List[ComponentVersion]]) -> List[ComponentVersion]:
    """先跑 loader，失败则用本地缓存兜底。"""
    try:
        versions = loader()
    except Exception as exc:
        cached, age = load_cached(key)
        if cached:
            print(f"[cache:{key}] 在线抓取失败（{exc}），回退本地缓存（{age}前）")
            return cached
        raise
    if versions:
        save_cached(key, versions)
    return versions
