# -*- coding: utf-8 -*-
"""下载镜像（加速源）管理。

GitHub Release 直连在国内/加速器环境下经常很慢。这里提供"前缀型"镜像
（把完整 URL 拼在镜像域名后面，由镜像代为回源），并支持：

  - auto：按真实 URL 抽样测速，自动选最快的通道，结果按主机缓存
  - 手动指定某个镜像 / 直连 / 自定义模板
  - 下载时镜像优先，失败自动回退直连

设置落在 SETTINGS_FILE 的 "download" 段，与工作空间设置同一文件、互不干扰。
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .constants import SETTINGS_DIR, SETTINGS_FILE
from .http import get as http_get
from .utils import ensure_dir

# 只有这些主机走镜像：其它站点（Apache / npm / 各厂商官方源）通常直连更快，
# 套前缀反而可能被镜像拒绝
MIRRORED_HOSTS = (
    "github.com",
    "api.github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "codeload.github.com",
)

PROBE_URL = ("https://github.com/farion1231/cc-switch/releases/download/"
             "v4.0.11/CC-Switch-v4.0.11-Windows-Portable.zip")


@dataclass
class Mirror:
    id: str
    name: str
    template: str = ""  # 形如 https://ghfast.top/{url}；空表示直连

    def url_for(self, url: str) -> str:
        if not self.template:
            return url
        return self.template.format(url=url)


# 预设镜像：都是"前缀代理"，不改写内容
PRESETS: List[Mirror] = [
    Mirror("ghfast", "ghfast.top", "https://ghfast.top/{url}"),
    Mirror("gh-proxy", "gh-proxy.com", "https://gh-proxy.com/{url}"),
    Mirror("ghproxy", "ghproxy.net", "https://ghproxy.net/{url}"),
    Mirror("gitmirror", "hub.gitmirror.com", "https://hub.gitmirror.com/{url}"),
]
DIRECT = Mirror("direct", "直连（不使用镜像）", "")


def preset_by_id(mid: str) -> Optional[Mirror]:
    for m in PRESETS:
        if m.id == mid:
            return m
    return None


class MirrorSettings:
    """镜像选择与测速结果的持久化。"""

    def __init__(self) -> None:
        self.mode: str = "auto"          # auto / direct / 预设 id / custom
        self.custom: str = ""            # 自定义模板，如 https://xxx.com/{url}
        self.fastest: Dict[str, str] = {}  # host -> mirror id
        self.parts: int = 4              # 并行分块数；1 表示不分块（单线程流式）

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> "MirrorSettings":
        s = cls()
        try:
            if SETTINGS_FILE.exists():
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                d = data.get("download") or {}
                s.mode = d.get("mode") or "auto"
                s.custom = d.get("custom") or ""
                s.fastest = dict(d.get("fastest") or {})
                s.parts = int(d.get("parts") or 4)
        except Exception:
            pass
        # 环境变量优先，方便临时对比：MURIG_DOWNLOAD_PARTS=1 关闭分块
        env_parts = os.environ.get("MURIG_DOWNLOAD_PARTS")
        if env_parts:
            try:
                s.parts = max(1, min(16, int(env_parts)))
            except ValueError:
                pass
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
            data["download"] = {
                "mode": self.mode,
                "custom": self.custom,
                "fastest": self.fastest,
                "parts": self.parts,
            }
            SETTINGS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------
    def custom_mirror(self) -> Mirror:
        return Mirror("custom", "自定义", self.custom.strip())

    def current_mirror(self) -> Optional[Mirror]:
        """当前生效的镜像；None 表示直连或需先测速。"""
        if self.mode == "direct":
            return None
        if self.mode == "custom":
            m = self.custom_mirror()
            return m if m.template else None
        if self.mode in ("auto", ""):
            return None
        return preset_by_id(self.mode)

    def fastest_for(self, url: str) -> Optional[Mirror]:
        host = (urlparse(url).hostname or "").lower()
        mid = self.fastest.get(host)
        return preset_by_id(mid) if mid else None

    def candidates(self, url: str) -> List[Mirror]:
        """返回按优先级排列的通道（镜像在前，直连兜底）。"""
        host = (urlparse(url).hostname or "").lower()
        if host not in MIRRORED_HOSTS:
            return [DIRECT]
        if self.mode == "direct":
            return [DIRECT]
        mirror = self.current_mirror()
        if mirror is None and self.mode in ("auto", ""):
            mirror = self.fastest_for(url)
        if mirror is None:
            return [DIRECT]
        return [mirror, DIRECT]

    # ------------------------------------------------------------------
    def probe(self, url: str, mirrors: Optional[List[Mirror]] = None,
              budget: int = 512 * 1024, timeout: float = 10.0) -> List[Tuple[str, str, float]]:
        """各通道抽样测速，返回 [(id, 名称, KB/s)]，按速度降序；失败为 -1。"""
        targets = mirrors or ([DIRECT] + PRESETS)

        def run(m: Mirror) -> Tuple[str, str, float]:
            start = time.time()
            got = 0
            try:
                r = http_get(
                    m.url_for(url), timeout=timeout, stream=True,
                    headers={"User-Agent": "MuRig", "Range": f"bytes=0-{budget - 1}"},
                )
                with r:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        got += len(chunk)
                        if got >= budget or time.time() - start > timeout:
                            break
            except Exception:
                return (m.id, m.name, -1.0)
            dt = max(time.time() - start, 1e-6)
            return (m.id, m.name, got / dt / 1024)

        with ThreadPoolExecutor(max_workers=min(6, len(targets))) as ex:
            results = list(ex.map(run, targets))
        results.sort(key=lambda x: -x[2])
        return results

    def auto_select(self, url: str,
                    on_note=None) -> Optional[Mirror]:
        """auto 模式：测速选出最快可用通道并缓存（按主机）。"""
        host = (urlparse(url).hostname or "").lower()
        results = self.probe(url)
        best: Optional[Mirror] = None
        for mid, _name, speed in results:
            if speed <= 0:
                continue
            m = DIRECT if mid == "direct" else preset_by_id(mid)
            if m is None:
                continue
            best = m
            break
        if best is None:
            if on_note:
                on_note("warn", "镜像测速全部失败，本次使用直连")
            return None
        # 抖动保护：镜像相对直连优势不足 15% 时仍走直连（少依赖第三方，更稳定）
        direct_speed = next((spd for mid, _n, spd in results if mid == "direct"), -1.0)
        best_speed = next((spd for mid, _n, spd in results if mid == best.id), 0.0)
        if best.id != "direct" and direct_speed > 0 and best_speed < direct_speed * 1.15:
            best = DIRECT
        self.fastest[host] = best.id
        self.save()
        if on_note:
            detail = "、".join(
                f"{name} {int(spd)} KB/s" if spd > 0 else f"{name} 不可用"
                for _i, name, spd in results
            )
            on_note("info", f"测速完成（{detail}），本次使用：{best.name}")
        return best


# 全局单例：启动时加载，UI 修改后即时 save
MIRRORS = MirrorSettings.load()
