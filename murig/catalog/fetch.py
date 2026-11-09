# -*- coding: utf-8 -*-
"""向各官方 API / 归档站点抓取最新版本列表。"""

from __future__ import annotations

import json
import os
import re as _re
from pathlib import PurePosixPath
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests

from ..core.constants import CURRENT_OS, IS_ARM
from ..core.http import get as http_get
from ..core.models import ComponentVersion
from .urls import *  # noqa: F401,F403  各组件 URL 构造函数

__all__ = [
    "_get", "_sort_semver_desc", "_mysql_mac_filename", "_fetch_apache_listing",
    "_MYSQL_PORTABLE_SERIES",
    "RateLimitError", "_github_releases", "_github_tags", "_github_asset_names",
    "fetch_jdk_versions", "fetch_maven_versions", "fetch_tomcat_versions",
    "fetch_python_versions", "fetch_node_versions", "fetch_mysql_versions",
    "fetch_git_versions", "fetch_conda_versions", "fetch_redis_versions",
    "fetch_es_versions", "fetch_ollama_versions",
    "fetch_hadoop_versions", "fetch_zookeeper_versions", "fetch_hive_versions",
    "fetch_hbase_versions", "fetch_spark_versions", "fetch_flink_versions",
    "fetch_kafka_versions", "fetch_claude_code_versions", "fetch_ccswitch_versions",
    "fetch_pg_versions", "fetch_opengauss_versions", "fetch_dameng_versions",
    "fetch_oceanbase_versions", "fetch_kingbase_versions", "fetch_yashandb_versions",
]


class RateLimitError(RuntimeError):
    """GitHub API 限流 / 代理拦截导致的 403、429。"""


def _http_error(url: str, exc: Exception, code: int) -> Exception:
    """把 4xx 转成带解决建议的异常（403/429 额外区分 API 限流）。"""
    if "api.github.com" in url:
        tip = "（可设置 GITHUB_TOKEN 提高配额，或设置 MURIG_GITHUB_API_BASE 走镜像）"
    else:
        tip = ""
    if code == 429:
        return RateLimitError(f"429 请求过于频繁，已被限流：{url}{tip}")
    if code == 403:
        return RateLimitError(f"403 被拒绝（多为 API 限流或代理拦截）：{url}{tip}")
    return exc


def _get(url: str, timeout: int = 10,
         headers: Optional[Dict[str, str]] = None) -> requests.Response:
    """抓取用的 GET：复用 core.http 的重试与证书降级，并把限流错误转成友好提示。"""
    try:
        return http_get(url, timeout=timeout, headers=headers)
    except requests.exceptions.HTTPError as e:
        code = getattr(getattr(e, "response", None), "status_code", 0)
        if code in (401, 403, 404, 429):
            raise _http_error(url, e, code)
        raise


# ---------------------------------------------------------------------------
# GitHub：匿名 API 只有 60 次/小时/IP，共享出口 IP（加速器 / 代理 / 公司网）
# 必然被打满。因此提供三级策略：
#   1) 带 Token 请求（5000 次/小时）+ 可配置镜像 MURIG_GITHUB_API_BASE
#   2) API 失败时绕开 API：releases.atom 取 tag，expanded_assets 取附件名
#   3) 仍失败则由 registry 的缓存层回退到本地缓存/内置清单
# ---------------------------------------------------------------------------
def _github_headers() -> Dict[str, str]:
    headers = {
        "User-Agent": "MuRig",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = (os.environ.get("MURIG_GITHUB_TOKEN")
             or os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_json(path: str, timeout: int = 12):
    """请求 GitHub API（支持 Token 与镜像地址）。"""
    base = (os.environ.get("MURIG_GITHUB_API_BASE")
            or "https://api.github.com").rstrip("/")
    return _get(base + path, timeout=timeout, headers=_github_headers()).json()


def _github_asset_names(owner: str, repo: str, tag: str) -> List[str]:
    """从 GitHub 的 expanded_assets 片段读取某 release 的附件名（不消耗 API 配额）。"""
    try:
        html = _get(
            f"https://github.com/{owner}/{repo}/releases/expanded_assets/{tag}",
            timeout=10,
        ).text
    except Exception:
        return []
    return _re.findall(r'href="[^"]*?/releases/download/[^"]*?/([^"/]+)"', html)


def _github_releases_fallback(owner: str, repo: str, limit: int) -> List[dict]:
    """API 不可用时的回退：releases.atom 取 tag + expanded_assets 取附件名。"""
    try:
        atom = _get(f"https://github.com/{owner}/{repo}/releases.atom", timeout=15).text
    except Exception as e:
        raise RuntimeError(f"GitHub 访问失败（API 与 releases.atom 均不可用）：{e}")
    tags = _re.findall(r"<id>tag:github\.com,2008:Repository/\d+/(.+?)</id>", atom)
    if not tags:
        raise RuntimeError(f"无法解析 {owner}/{repo} 的 releases.atom")
    result: List[dict] = []
    # 每个 tag 需要一次页面请求，这里取前 30 个（足够覆盖近几个大版本，
    # 也避免退化为上百次请求）
    for tag in tags[:min(limit, 30)]:
        names = _github_asset_names(owner, repo, tag)
        result.append({
            "tag_name": tag,
            "assets": [{
                "name": n,
                "browser_download_url":
                    f"https://github.com/{owner}/{repo}/releases/download/{tag}/{n}",
            } for n in names],
        })
    return result


def _github_releases(owner: str, repo: str, per_page: int = 30) -> List[dict]:
    """GitHub Releases 列表；API 限流/失败时自动回退到非 API 通道。"""
    try:
        return _github_json(f"/repos/{owner}/{repo}/releases?per_page={per_page}")
    except Exception:
        return _github_releases_fallback(owner, repo, per_page)


def _github_tags(owner: str, repo: str, per_page: int = 60) -> List[dict]:
    """GitHub Tags 列表；API 不可用时回退到 releases.atom 的 tag。"""
    try:
        return _github_json(f"/repos/{owner}/{repo}/tags?per_page={per_page}")
    except Exception:
        fallback = _github_releases_fallback(owner, repo, per_page)
        return [{"name": r["tag_name"]} for r in fallback]


def _sort_semver_desc(vs) -> list:
    def key(v: str):
        try:
            return tuple(int(x) for x in v.split("."))
        except ValueError:
            return (0,)
    return sorted(set(vs), key=key, reverse=True)


def fetch_jdk_versions() -> List[ComponentVersion]:
    """Adoptium Temurin 官方 API。"""
    data = _get("https://api.adoptium.net/v3/info/available_releases").json()
    releases = data.get("available_releases", [])
    lts = data.get("available_lts_releases", [])
    # releases 有时会遗漏最新 LTS —— 合并去重
    vs = sorted({int(v) for v in list(releases) + list(lts)}, reverse=True)
    result = []
    for v in vs:
        cv = ComponentVersion(
            version=str(v),
            url_map=_adoptium_jdk_url(str(v)),
            archive_map={"Windows": "zip", "Darwin": "tar.gz", "Linux": "tar.gz"},
        )
        if v in lts:
            cv.display_label = f"{v}  (LTS)"  # type: ignore[attr-defined]
        result.append(cv)
    return result


def fetch_maven_versions() -> List[ComponentVersion]:
    """扫 Apache 归档目录页。"""
    html = _get("https://archive.apache.org/dist/maven/maven-3/").text
    vs = _re.findall(r'href="(3\.\d+\.\d+)/"', html)
    return [_cv(v, _maven_urls(v)) for v in _sort_semver_desc(vs)]


def fetch_tomcat_versions() -> List[ComponentVersion]:
    """扫 tomcat-11 / 10 / 9 三个大版本。"""
    versions: List[str] = []
    for major in ("11", "10", "9"):
        try:
            html = _get(f"https://archive.apache.org/dist/tomcat/tomcat-{major}/").text
            versions.extend(_re.findall(rf'href="v({major}\.\d+\.\d+)/"', html))
        except Exception:
            continue
    if not versions:
        raise RuntimeError("Tomcat 版本列表为空")
    return [_cv(v, _tomcat_urls(v)) for v in _sort_semver_desc(versions)]


def fetch_python_versions() -> List[ComponentVersion]:
    """扫 python.org FTP 索引。"""
    html = _get("https://www.python.org/ftp/python/").text
    vs = _re.findall(r'href="(3\.\d+\.\d+)/"', html)
    # 只保留 3.6+
    vs = [v for v in vs if int(v.split(".")[1]) >= 6]
    return [_cv(v, _python_urls(v)) for v in _sort_semver_desc(vs)]


def fetch_node_versions() -> List[ComponentVersion]:
    """Node.js 官方 dist/index.json。"""
    data = _get("https://nodejs.org/dist/index.json").json()
    # 每个 minor 保留最新 patch，major 10+
    by_key: Dict[tuple, str] = {}
    lts_of_major: Dict[int, str] = {}
    for entry in data:
        v = entry["version"].lstrip("v")
        try:
            parts = tuple(int(x) for x in v.split("."))
        except ValueError:
            continue
        if parts[0] < 10:
            continue
        k = (parts[0], parts[1])
        if k not in by_key or parts > tuple(int(x) for x in by_key[k].split(".")):
            by_key[k] = v
        if entry.get("lts"):
            lts_of_major[parts[0]] = entry["lts"] if isinstance(entry["lts"], str) else "LTS"
    ordered = sorted(by_key.values(),
                     key=lambda v: tuple(int(x) for x in v.split(".")),
                     reverse=True)
    result: List[ComponentVersion] = []
    for v in ordered:
        cv = _cv(v, _node_urls(v))
        major = int(v.split(".")[0])
        if major in lts_of_major:
            cv.display_label = f"{v}  (LTS {lts_of_major[major]})"  # type: ignore[attr-defined]
        result.append(cv)
    return result


_MYSQL_PORTABLE_SERIES = {(9, 7), (8, 4), (8, 0), (5, 7)}


def _mysql_mac_filename(v: str) -> Optional[str]:
    """从归档接口取某版本 macOS 当前架构的真实 tar.gz 文件名；失败返回 None。"""
    arch = "arm64" if IS_ARM else "x86_64"
    try:
        html = _get(
            f"https://downloads.mysql.com/archives/community/?tpl=files&os=33&version={v}",
            timeout=8,
        ).text
        m = _re.search(
            rf"/archives/get/p/23/file/(mysql-{_re.escape(v)}-macos\d+-{arch}\.tar\.gz)",
            html,
        )
        return m.group(1) if m else None
    except Exception:
        return None


def fetch_mysql_versions() -> List[ComponentVersion]:
    """MySQL 归档页：主页面内嵌版本下拉（含 9.x LTS），解析后取有便携包的系列。

    Windows/Linux 命名规则固定；macOS 标签（macos14/15）随发布日期变化，逐个版本走
    os=33 归档片段解析真实文件名，失败再按版本号规则回退。
    """
    versions: List[str] = []
    try:
        html = _get("https://downloads.mysql.com/archives/community/", timeout=12).text
        # <select name="version"> 的选项值；只取有便携 tar/zip 的四个系列
        msel = _re.search(r'<select name="version".*?</select>', html, _re.S)
        if msel:
            for v in _re.findall(r'<option value="(\d+\.\d+\.\d+)"', msel.group(0)):
                tup = tuple(int(x) for x in v.split("."))
                if tup[:2] in _MYSQL_PORTABLE_SERIES:
                    versions.append(v)
    except Exception:
        pass
    if not versions:
        # 保底：一份手工维护的近期列表
        versions = [
            "9.7.1", "9.7.0",
            "8.4.10", "8.4.9", "8.4.5",
            "8.0.45", "8.0.43", "8.0.41", "8.0.37",
            "5.7.44",
        ]

    # macOS ARM64 没有 5.7 构建，列出来也是死链
    if CURRENT_OS == "Darwin" and IS_ARM:
        versions = [v for v in versions if not v.startswith("5.7.")]
    versions = versions[:12]

    # macOS：并发解析每个版本的真实文件名
    mac_names: Dict[str, Optional[str]] = {}
    if CURRENT_OS == "Darwin":
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as pool:
            for v, name in zip(versions, pool.map(_mysql_mac_filename, versions)):
                mac_names[v] = name

    result: List[ComponentVersion] = []
    for v in versions:
        url_map = _mysql_urls(v)
        resolved = mac_names.get(v)
        if resolved:
            url_map["Darwin"] = (
                f"https://downloads.mysql.com/archives/get/p/23/file/{resolved}"
            )
        result.append(_cv(v, url_map))
    return result


def fetch_git_versions() -> List[ComponentVersion]:
    """Git for Windows Releases（API 限流时回退 releases.atom）。"""
    data = _github_releases("git-for-windows", "git", 20)
    versions: List[str] = []
    for rel in data:
        tag = rel.get("tag_name", "")
        # tag 形如 "v2.45.2.windows.1"
        m = _re.match(r"^v(\d+\.\d+\.\d+)(?:\.\w+)?", tag)
        if m:
            versions.append(m.group(1))
    versions = _sort_semver_desc(versions)
    if not versions:
        raise RuntimeError("Git 版本列表为空")
    return [_cv(v, _git_urls(v)) for v in versions[:15]]


def fetch_conda_versions() -> List[ComponentVersion]:
    """Miniconda 归档索引。抓 index 页解析文件名。"""
    html = _get("https://repo.anaconda.com/miniconda/").text
    # 匹配形如 Miniconda3-py312_24.7.1-0-Windows-x86_64.exe
    matches = _re.findall(r"Miniconda3-(py\d+_[\d.\-]+)-(?:Windows|MacOSX|Linux)", html)
    versions = _sort_semver_desc(set(matches))
    # 保底：如果解析失败或列表太少
    if len(versions) < 3:
        versions = [
            "py312_24.7.1-0",
            "py311_24.7.1-0",
            "py310_24.5.0-0",
            "py39_24.5.0-0",
            "latest",
        ]

    def make_cv(v: str) -> ComponentVersion:
        # 安装器文件后缀：Windows .exe / mac & linux .sh
        ext_map = {"Windows": "exe", "Darwin": "sh", "Linux": "sh"}
        return ComponentVersion(
            version=v,
            url_map=_conda_urls(v),
            archive_map=ext_map,  # 复用字段承载扩展名
        )

    return [make_cv(v) for v in versions[:12]]


def fetch_redis_versions() -> List[ComponentVersion]:
    """扫 download.redis.io 官方发布目录。"""
    html = _get("https://download.redis.io/releases/").text
    vs = _re.findall(r'href="redis-(\d+\.\d+\.\d+)\.tar\.gz"', html)
    if not vs:
        raise RuntimeError("Redis 版本列表为空")
    return [_cv(v, _redis_urls(v)) for v in _sort_semver_desc(vs)[:15]]


def fetch_es_versions() -> List[ComponentVersion]:
    """Elasticsearch GitHub Tags（7.x 及以上）。"""
    data = _github_tags("elastic", "elasticsearch", 60)
    vs: List[str] = []
    for t in data:
        m = _re.fullmatch(r"v?(\d+\.\d+\.\d+)", t.get("name", ""))
        if m and int(m.group(1).split(".")[0]) >= 7:
            vs.append(m.group(1))
    if not vs:
        raise RuntimeError("Elasticsearch 版本列表为空")
    return [_cv(v, _es_urls(v)) for v in _sort_semver_desc(vs)[:15]]


def fetch_ollama_versions() -> List[ComponentVersion]:
    """Ollama GitHub Releases；只收录三平台便携包齐全（Linux 仍为 tgz）的版本。"""
    data = _github_releases("ollama", "ollama", 100)
    # 上游自 v0.13 起 Linux 包改用 .tar.zst（本工具未内置 zstd 解压），
    # 因此不再要求"三平台齐全"，只要求当前平台的分发包存在
    required_by_os = {
        "Windows": {"ollama-windows-amd64.zip"},
        "Darwin": {"Ollama-darwin.zip"},
        "Linux": {"ollama-linux-amd64.tgz"},
    }
    required = required_by_os.get(CURRENT_OS, {"ollama-windows-amd64.zip"})
    vs: List[str] = []
    for rel in data:
        m = _re.fullmatch(r"v(\d+\.\d+\.\d+)", rel.get("tag_name", ""))
        if not m:
            continue
        assets = {a["name"] for a in rel.get("assets", [])}
        if required <= assets:
            vs.append(m.group(1))
    if not vs:
        if CURRENT_OS == "Linux":
            raise RuntimeError(
                "Ollama 版本列表为空：上游 Linux 包已改为 .tar.zst，本工具暂不支持 zstd"
            )
        raise RuntimeError("Ollama 版本列表为空")
    return [_tgz_cv(v, _ollama_urls(v)) for v in vs[:12]]


def _fetch_apache_listing(listing_url: str, pattern: str) -> List[str]:
    """通用 Apache 归档目录扫描，返回去重、按版本号降序的列表。"""
    html = _get(listing_url).text
    vs = _re.findall(pattern, html)
    if not vs:
        raise RuntimeError(f"版本列表为空：{listing_url}")
    return _sort_semver_desc(set(vs))


def fetch_hadoop_versions() -> List[ComponentVersion]:
    vs = _fetch_apache_listing(
        f"{_APACHE_ARCHIVE}/hadoop/common/", r'href="hadoop-(\d+\.\d+\.\d+)/"'
    )
    return [_tgz_cv(v, _hadoop_urls(v)) for v in vs[:10]]


def fetch_zookeeper_versions() -> List[ComponentVersion]:
    vs = _fetch_apache_listing(
        f"{_APACHE_ARCHIVE}/zookeeper/", r'href="zookeeper-(\d+\.\d+\.\d+)/"'
    )
    return [_tgz_cv(v, _zookeeper_urls(v)) for v in vs[:10]]


def fetch_hive_versions() -> List[ComponentVersion]:
    vs = _fetch_apache_listing(
        f"{_APACHE_ARCHIVE}/hive/", r'href="hive-(\d+\.\d+\.\d+)/"'
    )
    return [_tgz_cv(v, _hive_urls(v)) for v in vs[:10]]


def fetch_hbase_versions() -> List[ComponentVersion]:
    vs = _fetch_apache_listing(
        f"{_APACHE_ARCHIVE}/hbase/", r'href="(\d+\.\d+\.\d+)/"'
    )
    return [_tgz_cv(v, _hbase_urls(v)) for v in vs[:10]]


def fetch_spark_versions() -> List[ComponentVersion]:
    vs = _fetch_apache_listing(
        f"{_APACHE_ARCHIVE}/spark/", r'href="spark-(\d+\.\d+\.\d+)/"'
    )
    return [_tgz_cv(v, _spark_urls(v)) for v in vs[:10]]


def fetch_flink_versions() -> List[ComponentVersion]:
    vs = _fetch_apache_listing(
        f"{_APACHE_ARCHIVE}/flink/", r'href="flink-(\d+\.\d+\.\d+)/"'
    )
    return [_tgz_cv(v, _flink_urls(v)) for v in vs[:10]]


def fetch_kafka_versions() -> List[ComponentVersion]:
    vs = _fetch_apache_listing(
        f"{_APACHE_ARCHIVE}/kafka/", r'href="(\d+\.\d+\.\d+)/"'
    )
    return [_tgz_cv(v, _kafka_urls(v)) for v in vs[:10]]


def fetch_claude_code_versions() -> List[ComponentVersion]:
    """npm registry：@anthropic-ai/claude-code 的稳定版本。"""
    d = _get("https://registry.npmjs.org/@anthropic-ai/claude-code").json()
    vs = [v for v in d.get("versions", {}) if _re.fullmatch(r"\d+\.\d+\.\d+", v)]
    vs.sort(key=lambda v: tuple(int(x) for x in v.split(".")), reverse=True)
    if not vs:
        raise RuntimeError("Claude Code 版本列表为空")
    # 不走 HTTP 下载（url 仅占位）；组件的 npm_package 字段触发 npm 便携安装流程
    return [
        ComponentVersion(v, {"Windows": "npm", "Darwin": "npm", "Linux": "npm"})
        for v in vs[:20]
    ]


def fetch_ccswitch_versions() -> List[ComponentVersion]:
    """CC-Switch GitHub Releases；要求 Win/macOS/Linux 三件套齐全。"""
    data = _github_releases("farion1231", "cc-switch", 30)
    result: List[ComponentVersion] = []
    for rel in data:
        m = _re.fullmatch(r"v(\d+\.\d+\.\d+)", rel.get("tag_name", ""))
        if not m:
            continue
        v = m.group(1)
        assets = {a["name"] for a in rel.get("assets", [])}
        urls = _ccswitch_urls(v)
        # 当前系统需要的分发包必须在 assets 里（Linux arm64 无包则跳过该版本）
        required = {PurePosixPath(urlparse(u).path).name for u in urls.values() if u}
        if not required <= assets:
            continue
        result.append(ComponentVersion(
            version=v,
            url_map=_ccswitch_urls(v),
            archive_map={"Windows": "zip", "Darwin": "tar.gz", "Linux": "bin"},
        ))
    if not result:
        raise RuntimeError("CC-Switch 版本列表为空")
    return result[:10]


def fetch_pg_versions() -> List[ComponentVersion]:
    """PostgreSQL 版本列表。

    ftp.postgresql.org 与各国内镜像的目录列表节点普遍是陈旧快照，无法取到最新版本，
    因此维护一份精选版本（各主版本的最新小版本），逐个 HEAD 校验官方源码包确实存在。
    """
    curated = ("18.4", "17.9", "16.13", "15.19", "14.24", "13.21")
    result: List[ComponentVersion] = []
    for v in curated:
        url = f"https://ftp.postgresql.org/pub/source/v{v}/postgresql-{v}.tar.gz"
        try:
            r = requests.head(
                url, timeout=10, allow_redirects=True,
                headers={"User-Agent": "MuRig"},
            )
            if r.status_code == 200:
                result.append(ComponentVersion(
                    version=v,
                    url_map=_pg_urls(v),
                    archive_map={"Windows": "zip", "Darwin": "zip", "Linux": "tar.gz"},
                ))
        except Exception:
            continue
    if not result:
        raise RuntimeError("PostgreSQL 版本校验全部失败")
    return result


def fetch_opengauss_versions() -> List[ComponentVersion]:
    """openGauss Lite：版本列表由官网前端 JS 动态渲染，维护已知版本并逐个 HEAD 校验。"""
    result: List[ComponentVersion] = []
    for v in ("7.0.0", "6.0.1", "6.0.0"):
        url = _opengauss_urls(v)["Linux"]
        try:
            r = requests.head(
                url, timeout=10, allow_redirects=True,
                headers={"User-Agent": "MuRig"},
            )
            if r.status_code == 200:
                result.append(_tgz_cv(v, _opengauss_urls(v)))
        except Exception:
            continue
    if not result:
        raise RuntimeError("openGauss 版本列表为空")
    return result


_DAMENG_OS_ID = {"Windows": "7", "Linux": "10"}  # Win_64 / rhel7 x86_64


_DAMENG_BASE = "https://download.dameng.com"


def fetch_dameng_versions() -> List[ComponentVersion]:
    """达梦生态下载 API：取当前系统最新 DM8 构建包。"""
    os_id = _DAMENG_OS_ID.get(CURRENT_OS)
    if not os_id:
        raise RuntimeError("达梦不支持当前系统")
    d = _get(
        f"https://eco.dameng.com/eco-download-server/cpu/os/table/download/32/0/{os_id}"
    ).json()
    path = d["result"]["url"]
    m = _re.search(r"/(20\d{2})(\d{2})/dm8_(\d{8})_", path)
    label = f"{m.group(1)}.{m.group(2)}.{m.group(3)[6:]}" if m else "latest"
    url = _DAMENG_BASE + path
    return [ComponentVersion(
        version=label,
        url_map={"Windows": url, "Linux": url, "Darwin": ""},
        archive_map={"Windows": "zip", "Linux": "zip"},
    )]


def fetch_oceanbase_versions() -> List[ComponentVersion]:
    """OceanBase CE GitHub Releases：取主服务 el7 x86_64 RPM。"""
    data = _github_releases("oceanbase", "oceanbase", 30)
    result: List[ComponentVersion] = []
    seen: set = set()
    for rel in data:
        for a in rel.get("assets", []):
            m = _re.fullmatch(
                r"oceanbase-ce-(\d+\.\d+\.\d+\.\d+)-\d+\.el7\.x86_64\.rpm", a["name"]
            )
            if not m:
                continue
            v = m.group(1)
            if v in seen:
                continue
            seen.add(v)
            result.append(ComponentVersion(
                version=v,
                url_map={"Windows": "", "Darwin": "", "Linux": a["browser_download_url"]},
                archive_map={"Linux": "rpm"},
            ))
    if not result:
        raise RuntimeError("OceanBase 版本列表为空")
    return result[:10]


def fetch_kingbase_versions() -> List[ComponentVersion]:
    """人大金仓 KingbaseES 官网 CMS：取免登录的 Linux 便携 server 包（金融版构建）。

    主流 GUI 安装 ISO 需申请，官网另发布免登录的 kingbase-server 便携 tar（bin/lib 标准
    布局，自带 license.dat）。OSS 开启了 Referer 防盗链，下载时组件会带上 Referer 头。
    """
    if CURRENT_OS != "Linux":
        raise RuntimeError("KingbaseES 便携 server 包仅支持 Linux")
    resp = requests.post(
        "https://www.kingbase.com.cn/cebest-cms/basic-content/other-versions-page-list",
        json={"kesId": 1, "page": 0, "size": 80},
        timeout=15,
        headers={"User-Agent": "MuRig"},
    )
    resp.raise_for_status()
    rows = resp.json()["data"]["content"]

    picked: List[tuple] = []
    seen: set = set()
    for r in rows:
        if r.get("operatingSystemName") != "Linux":
            continue
        fa = r.get("fileAddress") or ""
        m = _re.fullmatch(
            r"kingbase-server-(V\d{3}R\d{3}C\d{3}B\w+)-linux-(x86_64|KunPeng|aarch64)\.tar",
            fa.rsplit("/", 1)[-1],
        )
        if not m:
            continue
        build, plat = m.group(1), m.group(2)
        # 按当前机器架构过滤（ARM 行文件名多为 KunPeng，也有 aarch64）
        if (plat in ("KunPeng", "aarch64")) != IS_ARM:
            continue
        mm = _re.search(r"V(\d{3})R(\d{3})C(\d{3})B\d+PS(\d+)", build)
        label = (
            f"V{int(mm.group(1))}R{int(mm.group(2))}C{int(mm.group(3))} PS{int(mm.group(4))}"
            if mm else build
        )
        if label in seen:
            continue
        seen.add(label)
        picked.append((r.get("postTime") or "", ComponentVersion(
            version=build,
            display_label=label,
            url_map={"Windows": "", "Darwin": "", "Linux": fa},
            archive_map={"Linux": "tar"},
        )))
    if not picked:
        raise RuntimeError("KingbaseES 便携包列表为空")
    picked.sort(key=lambda t: t[0], reverse=True)
    return [cv for _, cv in picked[:6]]


def fetch_yashandb_versions() -> List[ComponentVersion]:
    """崖山数据库 YashanDB 官网 API：取企业版 Linux server 包（tar.gz 套内层数据库 tar）。"""
    if CURRENT_OS != "Linux":
        raise RuntimeError("YashanDB 仅提供 Linux 安装包")
    resp = requests.post(
        "https://www.yashandb.com/yashan-server/api/portal/software/findByCondition",
        json={"current": 1, "size": 30},
        timeout=15,
        headers={"User-Agent": "MuRig"},
    )
    resp.raise_for_status()
    rows = resp.json()["data"]["data"]

    picked: List[tuple] = []
    seen: set = set()
    for r in rows:
        if r.get("productName") != "YashanDB 企业版":
            continue
        raw = r.get("downloadUrl")
        if not raw:
            continue
        du = json.loads(raw)
        alt = du.get("alt") or ""
        # 只认 yashandb-<版本>-linux-<架构>.tar.gz；官网文件名可能带 " (2)" 尾缀；
        # yashandb-image-* 是 Docker 镜像包
        m = _re.fullmatch(
            r"yashandb-(\d+\.\d+\.\d+\.\d+)-linux-(x86_64|aarch64)"
            r"(?:\s*\(\d+\))?\.tar\.gz",
            alt.strip(),
        )
        if not m:
            continue
        v, plat = m.group(1), m.group(2)
        if (plat == "aarch64") != IS_ARM:
            continue
        if v in seen:
            continue
        seen.add(v)
        picked.append((r.get("releaseDate") or "", ComponentVersion(
            version=v,
            url_map={"Windows": "", "Darwin": "", "Linux": du["url"]},
            archive_map={"Linux": "tar.gz"},
        )))
    if not picked:
        raise RuntimeError("YashanDB 版本列表为空")
    picked.sort(key=lambda t: t[0], reverse=True)
    return [cv for _, cv in picked[:5]]
