# -*- coding: utf-8 -*-
"""软件更新检查：向 GitHub Releases 接口查询最新版本并与当前版本比较。

只用 Python 标准库 + 已有的 http.get（含重试与证书降级），不引入新依赖；
查询失败时抛异常，由调用方（后台线程）转成界面提示。
"""

from __future__ import annotations

import html
import re
from typing import NamedTuple, Tuple

from .constants import (
    APP_VERSION, RELEASES_API, RELEASES_ATOM, RELEASES_LATEST_URL,
)
from .http import get as http_get

__all__ = ["UpdateInfo", "fetch_latest", "version_key", "is_newer"]


class UpdateInfo(NamedTuple):
    """一个已发布版本的信息。"""

    version: str      # tag_name，如 "v1.2.2"
    url: str          # 发布页地址（供用户跳转下载）
    notes: str        # 更新说明（已截断）
    published: str    # 发布日期，如 "2026-10-15"


def version_key(text: str) -> Tuple[int, ...]:
    """把版本号转成可比较的元组：v1.2.1 -> (1, 2, 1)。

    非数字后缀（如 1.2.0-beta）会被忽略，只比较主干数字部分；
    完全解析不出数字时返回 (0,)，保证比较不抛异常。
    """
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums) or (0,)


def is_newer(latest: str, current: str = APP_VERSION) -> bool:
    """latest 是否比 current 新（位数不同时按 0 补齐比较）。"""
    a, b = version_key(latest), version_key(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def _strip_html(text: str) -> str:
    """订阅源里的更新说明是（可能被转义过的）HTML，转成可读纯文本。"""
    # 先反转义：atom 的 content 常把标签写成 &lt;p&gt;，否则下面的去标签会漏掉
    text = html.unescape(text)
    text = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    # 再反转义一次，处理 &amp;nbsp; 这类二次转义
    text = html.unescape(text)
    lines = [ln.strip() for ln in text.splitlines()]
    # 去掉连续空行
    out: list = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def _fetch_latest_api(timeout: int, on_note) -> UpdateInfo:
    """首选来源：GitHub Releases 接口（字段最全）。"""
    resp = http_get(
        RELEASES_API,
        timeout=timeout,
        headers={"User-Agent": "MuRig", "Accept": "application/vnd.github+json"},
        on_note=on_note,
    )
    data = resp.json()
    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        raise ValueError("接口未返回版本号（tag_name 为空）")
    body = (data.get("body") or "").strip()
    # 更新说明可能很长，界面上只展示前若干行
    lines = [ln.rstrip() for ln in body.splitlines()]
    notes = "\n".join(ln for ln in lines if ln)[:1200]
    return UpdateInfo(
        version=tag,
        url=str(data.get("html_url") or RELEASES_LATEST_URL),
        notes=notes,
        published=str(data.get("published_at") or "")[:10],
    )


def _fetch_latest_atom(timeout: int, on_note) -> UpdateInfo:
    """兜底来源：Releases 订阅源（接口限流 / 被墙时的退路）。

    未认证调用 api.github.com 只有 60 次/小时/IP，很容易被限流；
    github.com/<repo>/releases.atom 是普通网页资源，不受这条限流约束。
    """
    resp = http_get(
        RELEASES_ATOM,
        timeout=timeout,
        headers={"User-Agent": "MuRig"},
        on_note=on_note,
    )
    entries = re.findall(r"(?is)<entry>(.*?)</entry>", resp.text or "")
    if not entries:
        raise ValueError("发布订阅源里没有解析到任何版本")
    entry = entries[0]

    def _field(tag: str) -> str:
        m = re.search(rf"(?is)<{tag}[^>]*>(.*?)</{tag}>", entry)
        return (m.group(1) if m else "").strip()

    tag = _strip_html(_field("title"))
    if not tag:
        raise ValueError("发布订阅源里没有解析到版本号")
    # 优先取 text/html 的链接（发布页），否则退回通用发布页
    m = re.search(r'(?is)<link[^>]*type="text/html"[^>]*href="([^"]+)"', entry)
    url = html.unescape(m.group(1)) if m else RELEASES_LATEST_URL
    return UpdateInfo(
        version=tag,
        url=url,
        notes=_strip_html(_field("content"))[:1200],
        published=_field("updated")[:10],
    )


def fetch_latest(timeout: int = 10,
                 on_note=None) -> UpdateInfo:
    """查询 GitHub 上最新的 Release：接口优先，失败自动回退订阅源。

    两者都失败时抛出最后一次的异常（网络错误 / 无发布 / 限流等）。
    """
    try:
        return _fetch_latest_api(timeout, on_note)
    except Exception as exc:
        if on_note:
            on_note(f"GitHub 接口不可用（{exc.__class__.__name__}），改用发布订阅源重试…")
        return _fetch_latest_atom(timeout, on_note)
