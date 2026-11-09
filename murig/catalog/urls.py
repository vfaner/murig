# -*- coding: utf-8 -*-
"""各组件官方分发包的 URL 构造（离线清单的网络地址部分）。"""

from __future__ import annotations

from typing import Dict

from ..core.constants import CURRENT_OS, IS_ARM
from ..core.models import ComponentVersion

__all__ = [
    "_APACHE_ARCHIVE", "_STD_ARCHIVE", "_TGZ_ARCHIVE",
    "_adoptium_jdk_url", "_cv", "_tgz_cv",
    "_maven_urls", "_tomcat_urls",
    "_mysql_macos_tag", "_mysql_urls", "_mariadb_urls",
    "_python_urls", "_node_urls", "_git_urls", "_conda_urls",
    "_redis_urls", "_es_urls", "_ollama_urls", "_ccswitch_urls",
    "_hadoop_urls", "_zookeeper_urls", "_hive_urls", "_hbase_urls",
    "_spark_urls", "_flink_urls", "_kafka_urls",
    "_pg_urls", "_opengauss_urls", "_dameng_default_urls",
]


def _adoptium_jdk_url(version: str) -> Dict[str, str]:
    """
    Adoptium Temurin JDK 下载地址生成。

    注意：Adoptium 的实际最新构建 URL 会带 build 号，这里使用 latest release API 拼接的
    通用镜像地址；如果链接失效可自行替换为其他镜像（如华为云、清华镜像）。
    """
    # 使用 Adoptium API 提供的“latest binary redirect”地址：一次性重定向到最新构建
    base = "https://api.adoptium.net/v3/binary/latest"
    # 参数：feature_version/release_type/os/arch/image_type/jvm_impl/heap_size/vendor
    win = f"{base}/{version}/ga/windows/x64/jdk/hotspot/normal/eclipse"
    mac_arch = "aarch64" if IS_ARM else "x64"
    mac = f"{base}/{version}/ga/mac/{mac_arch}/jdk/hotspot/normal/eclipse"
    linux_arch = "aarch64" if IS_ARM else "x64"
    linux = f"{base}/{version}/ga/linux/{linux_arch}/jdk/hotspot/normal/eclipse"
    return {"Windows": win, "Darwin": mac, "Linux": linux}


# ---------------------------------------------------------------------------
# URL 构造器（模块级，便于抓取器与初始默认列表复用）
# ---------------------------------------------------------------------------
_STD_ARCHIVE: Dict[str, str] = {"Windows": "zip", "Darwin": "tar.gz", "Linux": "tar.gz"}


def _cv(version: str, url_map: Dict[str, str]) -> ComponentVersion:
    return ComponentVersion(version=version, url_map=url_map, archive_map=dict(_STD_ARCHIVE))


def _maven_urls(v: str) -> Dict[str, str]:
    base = f"https://archive.apache.org/dist/maven/maven-3/{v}/binaries/apache-maven-{v}-bin"
    return {"Windows": f"{base}.zip", "Darwin": f"{base}.tar.gz", "Linux": f"{base}.tar.gz"}


def _tomcat_urls(v: str) -> Dict[str, str]:
    major = v.split(".", 1)[0]
    base = f"https://archive.apache.org/dist/tomcat/tomcat-{major}/v{v}/bin/apache-tomcat-{v}"
    return {"Windows": f"{base}.zip", "Darwin": f"{base}.tar.gz", "Linux": f"{base}.tar.gz"}


def _mysql_macos_tag(v: str) -> str:
    """MySQL macOS 包的系统标签：新版本改打 Sequoia(15)，旧版本是 Sonoma(14)。

    实测边界：9.x 全系 macos15；8.4 ≥ 8.4.5、8.0 ≥ 8.0.41 为 macos15，其余 macos14。
    """
    try:
        tup = tuple(int(x) for x in v.split("."))
    except ValueError:
        return "macos14"
    if tup[0] >= 9:
        return "macos15"
    if tup[:2] == (8, 4) and tup >= (8, 4, 5):
        return "macos15"
    if tup[:2] == (8, 0) and tup >= (8, 0, 41):
        return "macos15"
    return "macos14"


def _mysql_urls(v: str) -> Dict[str, str]:
    major_minor = v.rsplit(".", 1)[0]
    win = f"https://dev.mysql.com/get/Downloads/MySQL-{major_minor}/mysql-{v}-winx64.zip"
    macos_tag = _mysql_macos_tag(v)
    if IS_ARM and CURRENT_OS == "Darwin":
        mac = f"https://dev.mysql.com/get/Downloads/MySQL-{major_minor}/mysql-{v}-{macos_tag}-arm64.tar.gz"
    else:
        mac = f"https://dev.mysql.com/get/Downloads/MySQL-{major_minor}/mysql-{v}-{macos_tag}-x86_64.tar.gz"
    linux = f"https://dev.mysql.com/get/Downloads/MySQL-{major_minor}/mysql-{v}-linux-glibc2.28-x86_64.tar.xz"
    return {"Windows": win, "Darwin": mac, "Linux": linux}


def _mariadb_urls(v: str) -> Dict[str, str]:
    """MariaDB 官方 archive 免登录直链：Linux systemd bintar（仅 x86_64）+ Windows x64 zip。"""
    root = f"https://archive.mariadb.org/mariadb-{v}"
    win = f"{root}/winx64-packages/mariadb-{v}-winx64.zip"
    # 官方 archive 无 aarch64 bintar；Linux ARM 请用发行版仓库
    linux = (
        f"{root}/bintar-linux-systemd-x86_64/mariadb-{v}-linux-systemd-x86_64.tar.gz"
        if not IS_ARM else ""
    )
    return {"Windows": win, "Darwin": "", "Linux": linux}


def _python_urls(v: str) -> Dict[str, str]:
    win = f"https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip"
    mac = f"https://www.python.org/ftp/python/{v}/Python-{v}.tgz"
    linux = f"https://www.python.org/ftp/python/{v}/Python-{v}.tgz"
    return {"Windows": win, "Darwin": mac, "Linux": linux}


def _node_urls(v: str) -> Dict[str, str]:
    base = f"https://nodejs.org/dist/v{v}/node-v{v}"
    win = f"{base}-win-x64.zip"
    mac_arch = "arm64" if IS_ARM else "x64"
    mac = f"{base}-darwin-{mac_arch}.tar.gz"
    linux = f"{base}-linux-x64.tar.gz"
    return {"Windows": win, "Darwin": mac, "Linux": linux}


def _git_urls(v: str) -> Dict[str, str]:
    """
    Git 下载：
      - Windows: MinGit（便携版，解压即用）
      - macOS/Linux: 通常系统自带 git，或用户自己 brew install / apt-get 安装。
        这里提供源码 tar.gz 作为占位下载（不做编译，仅作展示）。
    """
    win = (
        f"https://github.com/git-for-windows/git/releases/download/"
        f"v{v}.windows.1/MinGit-{v}-64-bit.zip"
    )
    src = f"https://github.com/git/git/archive/refs/tags/v{v}.tar.gz"
    return {"Windows": win, "Darwin": src, "Linux": src}


def _conda_urls(v: str) -> Dict[str, str]:
    """
    Miniconda 安装器：
      - Windows: .exe
      - macOS:   .sh (根据架构挑 arm64 / x86_64)
      - Linux:   .sh
    版本号如 "py312_24.7.1-0"。
    """
    base = "https://repo.anaconda.com/miniconda"
    win = f"{base}/Miniconda3-{v}-Windows-x86_64.exe"
    mac_arch = "arm64" if IS_ARM else "x86_64"
    mac = f"{base}/Miniconda3-{v}-MacOSX-{mac_arch}.sh"
    linux = f"{base}/Miniconda3-{v}-Linux-x86_64.sh"
    return {"Windows": win, "Darwin": mac, "Linux": linux}


# ---------------------------------------------------------------------------
# 数据库 / 大数据 / AI 组件 URL 构造器
# ---------------------------------------------------------------------------
_APACHE_ARCHIVE = "https://archive.apache.org/dist"


# 三平台统一 tar.gz 的归档映射（Windows 自带 tar 也可解压，包内含 .cmd 脚本）
_TGZ_ARCHIVE: Dict[str, str] = {"Windows": "tar.gz", "Darwin": "tar.gz", "Linux": "tar.gz"}


def _tgz_cv(version: str, url_map: Dict[str, str]) -> ComponentVersion:
    return ComponentVersion(version=version, url_map=url_map, archive_map=dict(_TGZ_ARCHIVE))


def _redis_urls(v: str) -> Dict[str, str]:
    """Redis：Windows 用 redis-windows 社区移植版（msys2 构建）；macOS/Linux 用官方源码包。"""
    win = (
        "https://github.com/redis-windows/redis-windows/releases/download/"
        f"{v}/Redis-{v}-Windows-x64-msys2.zip"
    )
    src = f"https://download.redis.io/releases/redis-{v}.tar.gz"
    return {"Windows": win, "Darwin": src, "Linux": src}


def _es_urls(v: str) -> Dict[str, str]:
    """Elasticsearch 官方分发包（Windows zip / macOS·Linux tar.gz）。"""
    base = "https://artifacts.elastic.co/downloads/elasticsearch"
    win = f"{base}/elasticsearch-{v}-windows-x86_64.zip"
    major = int(v.split(".")[0])
    # 7.x 没有 arm64 的 macOS 包
    if IS_ARM and major >= 8:
        mac = f"{base}/elasticsearch-{v}-darwin-aarch64.tar.gz"
    else:
        mac = f"{base}/elasticsearch-{v}-darwin-x86_64.tar.gz"
    linux = f"{base}/elasticsearch-{v}-linux-x86_64.tar.gz"
    return {"Windows": win, "Darwin": mac, "Linux": linux}


def _ollama_urls(v: str) -> Dict[str, str]:
    """Ollama GitHub Releases 便携包。

    注意：v0.13.0 起 Linux 包改用 .tar.zst，本工具不内置 zstd 解压，因此只收录
    v0.12.9 及以前的版本（抓取器同样会过滤）。
    """
    base = f"https://github.com/ollama/ollama/releases/download/v{v}"
    return {
        "Windows": f"{base}/ollama-windows-amd64.zip",
        "Darwin": f"{base}/Ollama-darwin.zip",
        "Linux": f"{base}/ollama-linux-amd64.tgz",
    }


def _hadoop_urls(v: str) -> Dict[str, str]:
    url = f"{_APACHE_ARCHIVE}/hadoop/common/hadoop-{v}/hadoop-{v}.tar.gz"
    return {"Windows": url, "Darwin": url, "Linux": url}


def _zookeeper_urls(v: str) -> Dict[str, str]:
    # 官方只发 tar.gz（Windows 解压后使用 bin 下的 .cmd 脚本）
    url = f"{_APACHE_ARCHIVE}/zookeeper/zookeeper-{v}/apache-zookeeper-{v}-bin.tar.gz"
    return {"Windows": url, "Darwin": url, "Linux": url}


def _hive_urls(v: str) -> Dict[str, str]:
    url = f"{_APACHE_ARCHIVE}/hive/hive-{v}/apache-hive-{v}-bin.tar.gz"
    return {"Windows": url, "Darwin": url, "Linux": url}


def _hbase_urls(v: str) -> Dict[str, str]:
    url = f"{_APACHE_ARCHIVE}/hbase/{v}/hbase-{v}-bin.tar.gz"
    return {"Windows": url, "Darwin": url, "Linux": url}


def _spark_urls(v: str) -> Dict[str, str]:
    url = f"{_APACHE_ARCHIVE}/spark/spark-{v}/spark-{v}-bin-hadoop3.tgz"
    return {"Windows": url, "Darwin": url, "Linux": url}


def _flink_urls(v: str) -> Dict[str, str]:
    url = f"{_APACHE_ARCHIVE}/flink/flink-{v}/flink-{v}-bin-scala_2.12.tgz"
    return {"Windows": url, "Darwin": url, "Linux": url}


def _kafka_urls(v: str) -> Dict[str, str]:
    url = f"{_APACHE_ARCHIVE}/kafka/{v}/kafka_2.13-{v}.tgz"
    return {"Windows": url, "Darwin": url, "Linux": url}


# ---------------------------------------------------------------------------
# AI 工具 / 主流数据库 / 信创数据库 URL 构造器
# ---------------------------------------------------------------------------
def _ccswitch_urls(v: str) -> Dict[str, str]:
    """CC-Switch（farion1231/cc-switch）GitHub Releases。"""
    base = f"https://github.com/farion1231/cc-switch/releases/download/v{v}"
    # Windows 便携版按系统架构区分；macOS 包为通用包；Linux AppImage 仅收录 x86_64
    win_seg = "Windows-arm64-" if (IS_ARM and CURRENT_OS == "Windows") else "Windows-"
    return {
        "Windows": f"{base}/CC-Switch-v{v}-{win_seg}Portable.zip",
        "Darwin": f"{base}/CC-Switch-v{v}-macOS.tar.gz",
        # AppImage：下载后 chmod +x 直接运行（bin 模式，不解压）
        "Linux": "" if IS_ARM else f"{base}/CC-Switch-v{v}-Linux-x86_64.AppImage",
    }


def _pg_urls(v: str) -> Dict[str, str]:
    """PostgreSQL：Win/macOS 用 EDB 免安装二进制 zip；Linux 用官方源码编译。"""
    return {
        "Windows": (
            "https://get.enterprisedb.com/postgresql/"
            f"postgresql-{v}-1-windows-x64-binaries.zip"
        ),
        "Darwin": (
            "https://get.enterprisedb.com/postgresql/"
            f"postgresql-{v}-1-osx-binaries.zip"
        ),
        "Linux": f"https://ftp.postgresql.org/pub/source/v{v}/postgresql-{v}.tar.gz",
    }


def _opengauss_urls(v: str) -> Dict[str, str]:
    """openGauss Lite（极简版），仅 Linux；选 CentOS7 包（glibc 2.17，兼容性最好）。"""
    url = (
        "https://opengauss.obs.cn-south-1.myhuaweicloud.com/"
        f"{v}/CentOS7/x86/openGauss-Lite-{v}-CentOS7-x86_64.tar.gz"
    )
    return {"Windows": "", "Darwin": "", "Linux": url}


def _dameng_default_urls() -> Dict[str, str]:
    """达梦 DM8 开发版固定链接（2026 年 7-8 月构建，已验证可下；抓取器会刷新成最新月份）。"""
    base = "https://download.dameng.com/eco/adapter/DM8"
    return {
        "Windows": f"{base}/202607/dm8_20260709_x86_win_64.zip",
        "Linux": f"{base}/202607/dm8_20260710_x86_rh7_64.zip",
        "Darwin": "",
    }
