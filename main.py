# -*- coding: utf-8 -*-
"""
MuRig - 编程开发环境自动装配小工具
==================================

Copyright (c) 2026 rgh
Licensed under the MIT License. See LICENSE file (or the README) for details.

一个基于 PySide6 的跨平台桌面 GUI 工具，用于自动下载、解压并配置常用开发环境组件：
JDK、Maven、Tomcat、MySQL、MariaDB、PostgreSQL、Redis、Elasticsearch、Python、Miniconda、
Node.js、Git、Hadoop、ZooKeeper、Hive、HBase、Spark、Flink、Kafka、Ollama、Claude Code、
CC-Switch、openGauss、达梦 DM8、OceanBase、SQL Server、TiDB、人大金仓 KingbaseES、
崖山 YashanDB。

组件按 Java / Python / 前端 / 数据库 / 大数据 / AI 六大类组织，支持按软件名、
别名或分类名模糊搜索。

用法：
    python main.py
"""

from __future__ import annotations

import base64
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import traceback
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

import requests

# ---------------------------------------------------------------------------
# PySide6 依赖
# ---------------------------------------------------------------------------
try:
    from PySide6.QtCore import (
        QEvent,
        QObject,
        QPoint,
        QSize,
        Qt,
        QThread,
        QTimer,
        Signal,
    )
    from PySide6.QtGui import (
        QAction,
        QColor,
        QCursor,
        QFont,
        QIcon,
        QPainter,
        QPixmap,
        QDesktopServices,
    )
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QCompleter,
        QDialog,
        QFileDialog,
        QFrame,
        QGraphicsDropShadowEffect,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpacerItem,
        QSplitter,
        QTabWidget,
        QTextEdit,
        QToolTip,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtCore import QSortFilterProxyModel
except ImportError:  # pragma: no cover
    print("缺少依赖 PySide6，请先执行:  pip install -r requirements.txt")
    raise


# ---------------------------------------------------------------------------
# 全局常量与工具函数
# ---------------------------------------------------------------------------
APP_NAME = "MuRig - 编程开发环境自动装配小工具"
APP_VERSION = "v1.1.0"
CONFIG_DIR = Path.home() / ".env-tools"
CONFIG_FILE = CONFIG_DIR / "config.json"

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


def human_size(num: float) -> str:
    """把字节数转换为可读字符串。"""
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def ensure_dir(path: Path) -> None:
    """确保目录存在。"""
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 组件定义
# ---------------------------------------------------------------------------
@dataclass
class ComponentVersion:
    """描述一个组件版本对应的下载 URL 及归档格式。"""

    version: str
    url_map: Dict[str, str]  # {"Windows": url, "Darwin": url, "Linux": url}
    archive_map: Dict[str, str] = field(default_factory=dict)  # 归档类型：zip / tar.gz / tar / rpm
    # 下拉框展示文案（为空则展示 version）；version 仍作为唯一标识使用
    display_label: Optional[str] = None

    def url_for_current(self) -> Optional[str]:
        return self.url_map.get(CURRENT_OS)

    def archive_for_current(self) -> str:
        if CURRENT_OS in self.archive_map:
            return self.archive_map[CURRENT_OS]
        url = self.url_for_current() or ""
        if url.endswith(".zip"):
            return "zip"
        if url.endswith(".tar.gz") or url.endswith(".tgz"):
            return "tar.gz"
        if url.endswith(".rpm"):
            return "rpm"
        if url.endswith(".tar"):
            return "tar"
        # AppImage / 无归档后缀的独立可执行文件 → 直接下载使用
        return "bin"


@dataclass
class Component:
    """一个开发环境组件的抽象。"""

    key: str  # 内部标识，例如 "jdk"
    display_name: str  # 显示名称
    env_var: Optional[str]  # 需要设置的 XXX_HOME 环境变量名，无则为 None
    path_subdir: str  # 需要加入 PATH 的子目录，一般为 "bin"（Windows 上也可能是 "Scripts"）
    exec_name: Optional[str] = None  # 用于探测的可执行文件名，不含扩展名
    version_args: List[str] = field(default_factory=lambda: ["--version"])  # 获取版本号的参数
    versions: List[ComponentVersion] = field(default_factory=list)
    # 安装器模式：某些组件（如 Miniconda）下载的是安装器而非归档，需要静默执行安装器
    installer_mode: bool = False
    # 安装器静默安装参数：按 CURRENT_OS 键取。执行时会附加安装目标目录参数
    installer_args: Dict[str, List[str]] = field(default_factory=dict)
    # 所属分类 key（见 CATEGORIES）
    category: str = "java"
    # 搜索别名（缩写 / 俗称），模糊搜索时一并参与匹配
    aliases: List[str] = field(default_factory=list)
    # 解压后需要在安装目录内依次执行的命令（如 Redis 源码执行 make 编译）
    after_extract: Optional[List[List[str]]] = None
    # 可执行文件可能所在的额外子目录（探测 / 配置 PATH 用），"" 表示安装根目录
    extra_bin_dirs: List[str] = field(default_factory=list)
    # npm 包名（如 "@anthropic-ai/claude-code"）：设置后不走下载，直接用本机 npm 便携安装
    npm_package: Optional[str] = None
    # 安装完成后展示给用户的额外操作提示（如达梦：请挂载 ISO 运行安装器）
    post_notes: List[str] = field(default_factory=list)
    # archive_map 为 "bin"（独立可执行文件）时，下载后统一重命名成的名字（方便 PATH 查找）
    raw_bin_name: Optional[str] = None
    # 下载时附加的自定义请求头（如 Kingbase OSS 需要 Referer 才能通过防盗链校验）
    download_headers: Dict[str, str] = field(default_factory=dict)
    # PATH / XXX_HOME 都找不到时，再扫的标准安装路径（支持 glob 通配，如
    # "C:/Program Files/MySQL/MySQL Server *"；macOS 官方 pkg 的 /usr/local/mysql）
    well_known_homes: List[str] = field(default_factory=list)

    def install_dir(self, version: str) -> Path:
        """返回该版本组件的解压安装目录。"""
        return CONFIG_DIR / self.key / f"{self.key}-{version}"

    def exec_path_in_home(self, home: str) -> Optional[Path]:
        """在给定 XXX_HOME 目录下查找可执行文件。"""
        if not self.exec_name:
            return None
        # Windows 下 npm/.bin 这类目录里可执行文件可能是 .cmd / .bat 而非 .exe
        exe_names = [self.exec_name + s for s in (
            (".exe", ".cmd", ".bat") if CURRENT_OS == "Windows" else ("",)
        )]
        # 依次尝试 path_subdir、extra_bin_dirs、常见默认目录与根目录（去重保序）
        candidate_dirs: List[str] = []
        for sub in [self.path_subdir, *self.extra_bin_dirs, "bin", "Scripts", "condabin", ""]:
            if sub not in candidate_dirs:
                candidate_dirs.append(sub)
        for sub in candidate_dirs:
            for exe in exe_names:
                cand = Path(home) / sub / exe if sub else Path(home) / exe
                if cand.exists():
                    return cand
        return None

    def detect(self) -> "DetectResult":
        """探测该组件是否已在系统中可用。"""
        if not self.exec_name:
            return DetectResult(False)

        # 1) 优先通过 XXX_HOME 环境变量判断
        if self.env_var:
            home = EnvManager.get(self.env_var)
            if home:
                exe = self.exec_path_in_home(home)
                if exe is not None:
                    return DetectResult(
                        installed=True,
                        source=self.env_var,
                        home=home,
                        exe_path=str(exe),
                        version_text=_probe_version(str(exe), self.version_args),
                    )

        # 2) 通过 PATH 中的可执行文件
        exe_name_final = self.exec_name + (".exe" if CURRENT_OS == "Windows" else "")
        which = shutil.which(exe_name_final) or shutil.which(self.exec_name)
        if which:
            return DetectResult(
                installed=True,
                source="PATH",
                exe_path=which,
                version_text=_probe_version(which, self.version_args),
            )

        # 3) 扫描官方安装器常用的标准路径（如 macOS 官方 pkg 的 /usr/local/mysql）
        import glob as _glob
        for raw in self.well_known_homes:
            for home in sorted(_glob.glob(raw)):
                exe = self.exec_path_in_home(home)
                if exe is not None:
                    return DetectResult(
                        installed=True,
                        source="标准安装路径",
                        home=home,
                        exe_path=str(exe),
                        version_text=_probe_version(str(exe), self.version_args),
                    )

        return DetectResult(False)


@dataclass
class DetectResult:
    """系统级探测结果。"""

    installed: bool
    source: str = ""  # "JAVA_HOME" / "PATH" / ""
    home: str = ""
    exe_path: str = ""
    version_text: str = ""


def _probe_version(exe: str, args: List[str]) -> str:
    """调用可执行文件抓取版本号；失败返回空串。"""
    try:
        proc = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        line = next((ln.strip() for ln in out.splitlines() if ln.strip()), "")
        return line[:80]
    except Exception:
        return ""


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


# ---------------------------------------------------------------------------
# 官网版本抓取器
# 每个函数负责通过官网 API / 目录列表拿到该组件所有可下载版本。
# 抓取失败会抛异常，调用方需要回退到硬编码默认列表。
# ---------------------------------------------------------------------------
import re as _re


def _get(url: str, timeout: int = 10) -> requests.Response:
    """带自动重试与 SSL 降级的 GET 请求。

    - 网络抖动/临时错误：最多重试 3 次，指数退避（1s, 2s）
    - SSL 错误（企业代理 MITM / 系统证书缺失等）：最后一次尝试关闭 SSL 校验
    """
    import time as _time
    headers = {"User-Agent": "MuRig"}
    last_exc: Optional[Exception] = None
    for attempt in range(3):
        try:
            if attempt < 2:
                r = requests.get(url, timeout=timeout, headers=headers)
            else:
                # 最后一次：关闭 SSL 校验，让企业代理/自签证书场景也能工作
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                r = requests.get(url, timeout=timeout, headers=headers, verify=False)
            r.raise_for_status()
            return r
        except requests.exceptions.SSLError as e:
            last_exc = e
            # SSL 错误直接进入下一次尝试
        except Exception as e:
            last_exc = e
        if attempt < 2:
            _time.sleep(1 << attempt)  # 1s, 2s
    assert last_exc is not None
    raise last_exc


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
    """Git for Windows Releases API。"""
    data = _get("https://api.github.com/repos/git-for-windows/git/releases?per_page=20").json()
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
    data = _get(
        "https://api.github.com/repos/elastic/elasticsearch/tags?per_page=60"
    ).json()
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
    data = _get(
        "https://api.github.com/repos/ollama/ollama/releases?per_page=100"
    ).json()
    required = {"ollama-windows-amd64.zip", "Ollama-darwin.zip", "ollama-linux-amd64.tgz"}
    vs: List[str] = []
    for rel in data:
        m = _re.fullmatch(r"v(\d+\.\d+\.\d+)", rel.get("tag_name", ""))
        if not m:
            continue
        assets = {a["name"] for a in rel.get("assets", [])}
        if required <= assets:
            vs.append(m.group(1))
    if not vs:
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
    data = _get(
        "https://api.github.com/repos/farion1231/cc-switch/releases?per_page=30"
    ).json()
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
    data = _get(
        "https://api.github.com/repos/oceanbase/oceanbase/releases?per_page=30"
    ).json()
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


FETCHERS: Dict[str, Callable[[], List[ComponentVersion]]] = {
    "jdk": fetch_jdk_versions,
    "maven": fetch_maven_versions,
    "tomcat": fetch_tomcat_versions,
    "python": fetch_python_versions,
    "node": fetch_node_versions,
    "mysql": fetch_mysql_versions,
    "git": fetch_git_versions,
    "conda": fetch_conda_versions,
    "redis": fetch_redis_versions,
    "elasticsearch": fetch_es_versions,
    "ollama": fetch_ollama_versions,
    "hadoop": fetch_hadoop_versions,
    "zookeeper": fetch_zookeeper_versions,
    "hive": fetch_hive_versions,
    "hbase": fetch_hbase_versions,
    "spark": fetch_spark_versions,
    "flink": fetch_flink_versions,
    "kafka": fetch_kafka_versions,
    "claude-code": fetch_claude_code_versions,
    "cc-switch": fetch_ccswitch_versions,
    "postgresql": fetch_pg_versions,
    "opengauss": fetch_opengauss_versions,
    "dameng": fetch_dameng_versions,
    "oceanbase": fetch_oceanbase_versions,
    "kingbase": fetch_kingbase_versions,
    "yashandb": fetch_yashandb_versions,
}


class VersionFetchWorker(QThread):
    """在后台线程里跑抓取器，避免阻塞 UI。"""

    done = Signal(str, object)  # (component_key, versions or None)

    def __init__(self, key: str, fetcher: Callable[[], List[ComponentVersion]],
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.key = key
        self.fetcher = fetcher

    def run(self) -> None:  # noqa: D401
        try:
            vs = self.fetcher()
            self.done.emit(self.key, vs)
        except Exception as exc:  # pragma: no cover
            print(f"[fetch:{self.key}] {exc}")
            self.done.emit(self.key, None)


def build_components() -> List[Component]:
    """构造预置的组件与版本信息（作为抓取完成前的默认列表）。"""

    components: List[Component] = []

    # ------------------ JDK ------------------
    components.append(
        Component(
            key="jdk",
            display_name="JDK (Temurin)",
            env_var="JAVA_HOME",
            path_subdir="bin",
            exec_name="java",
            version_args=["-version"],
            versions=[
                ComponentVersion(
                    version=v,
                    url_map=_adoptium_jdk_url(v),
                    archive_map={"Windows": "zip", "Darwin": "tar.gz", "Linux": "tar.gz"},
                )
                for v in ("21", "17", "11", "8")
            ],
            category="java",
            aliases=["java", "temurin", "jre"],
        )
    )

    # ------------------ Maven ------------------
    components.append(
        Component(
            key="maven",
            display_name="Apache Maven",
            env_var="MAVEN_HOME",
            path_subdir="bin",
            exec_name="mvn",
            version_args=["-v"],
            versions=[_cv(v, _maven_urls(v)) for v in ("3.9.6", "3.9.5", "3.8.8", "3.6.3")],
            category="java",
        )
    )

    # ------------------ Tomcat ------------------
    components.append(
        Component(
            key="tomcat",
            display_name="Apache Tomcat",
            env_var="CATALINA_HOME",
            path_subdir="bin",
            exec_name="catalina",
            version_args=["version"],
            versions=[_cv(v, _tomcat_urls(v)) for v in ("10.1.24", "9.0.89", "8.5.100")],
            category="java",
        )
    )

    # ------------------ MySQL ------------------
    components.append(
        Component(
            key="mysql",
            display_name="MySQL Server",
            env_var="MYSQL_HOME",
            path_subdir="bin",
            exec_name="mysql",
            version_args=["--version"],
            # macOS ARM64 无 5.7 构建，默认列表里不放死链
            versions=[_cv(v, _mysql_urls(v)) for v in (
                ("9.7.1", "8.4.10", "8.0.45", "8.0.37")
                if CURRENT_OS == "Darwin" and IS_ARM
                else ("9.7.1", "8.4.10", "8.0.45", "8.0.37", "5.7.44")
            )],
            category="database",
            well_known_homes=[
                # macOS 官方 pkg（/usr/local/mysql 是版本目录的符号链接）
                "/usr/local/mysql",
                "/opt/homebrew/opt/mysql",
                "/usr/local/opt/mysql",
                # Windows MySQL Installer / MSI
                "C:/Program Files/MySQL/MySQL Server *",
                "C:/Program Files (x86)/MySQL/MySQL Server *",
            ],
        )
    )

    # ------------------ Python ------------------
    components.append(
        Component(
            key="python",
            display_name="Python",
            env_var=None,
            path_subdir="Scripts" if CURRENT_OS == "Windows" else "bin",
            exec_name="python3" if CURRENT_OS != "Windows" else "python",
            version_args=["--version"],
            versions=[_cv(v, _python_urls(v)) for v in ("3.12.4", "3.11.9", "3.10.14", "3.9.19")],
            category="python",
        )
    )

    # ------------------ Node.js ------------------
    components.append(
        Component(
            key="node",
            display_name="Node.js",
            env_var="NODE_HOME",
            path_subdir="bin",
            exec_name="node",
            version_args=["--version"],
            versions=[_cv(v, _node_urls(v)) for v in ("20.15.0", "18.20.3", "16.20.2")],
            category="frontend",
            aliases=["node", "npm"],
        )
    )

    # ------------------ Git ------------------
    # macOS/Linux 一般依赖系统自带 git；Windows 用 MinGit 便携版
    components.append(
        Component(
            key="git",
            display_name="Git",
            env_var=None,
            path_subdir="cmd" if CURRENT_OS == "Windows" else "bin",
            exec_name="git",
            version_args=["--version"],
            versions=[_cv(v, _git_urls(v)) for v in ("2.45.2", "2.44.0", "2.43.0")],
            category="frontend",
        )
    )

    # ------------------ Miniconda ------------------
    # 安装器模式：exe/sh 静默安装到 install_dir
    conda_versions = []
    for v in ("py312_24.7.1-0", "py311_24.7.1-0", "py310_24.5.0-0"):
        cv = ComponentVersion(
            version=v,
            url_map=_conda_urls(v),
            archive_map={"Windows": "exe", "Darwin": "sh", "Linux": "sh"},
        )
        conda_versions.append(cv)
    components.append(
        Component(
            key="conda",
            display_name="Miniconda",
            env_var="CONDA_HOME",
            path_subdir="Scripts" if CURRENT_OS == "Windows" else "bin",
            exec_name="conda",
            version_args=["--version"],
            versions=conda_versions,
            installer_mode=True,
            installer_args={
                # /S = silent, /D=path 必须放最后
                "Windows": ["/S", "/InstallationType=JustMe", "/RegisterPython=0", "/AddToPath=0"],
                # -b batch, -f force overwrite, -p prefix
                "Darwin": ["-b", "-f", "-p"],
                "Linux": ["-b", "-f", "-p"],
            },
            category="python",
        )
    )

    # ------------------ Redis ------------------
    # Windows 走 redis-windows 移植版 zip；macOS/Linux 为官方源码包，解压后自动 make 编译
    components.append(
        Component(
            key="redis",
            display_name="Redis",
            env_var="REDIS_HOME",
            path_subdir="bin",
            exec_name="redis-server",
            version_args=["--version"],
            versions=[_cv(v, _redis_urls(v)) for v in ("8.4.7", "7.4.11", "7.2.16", "6.2.24")],
            category="database",
            aliases=["缓存", "cache"],
            # 源码包需要编译；产物在 src/ 目录
            after_extract=[["make", "-j4"]] if CURRENT_OS != "Windows" else None,
            extra_bin_dirs=["src"] if CURRENT_OS != "Windows" else [],
        )
    )

    # ------------------ Elasticsearch ------------------
    components.append(
        Component(
            key="elasticsearch",
            display_name="Elasticsearch",
            env_var="ES_HOME",
            path_subdir="bin",
            exec_name="elasticsearch",
            version_args=["--version"],
            versions=[_cv(v, _es_urls(v)) for v in ("8.15.2", "7.17.24")],
            category="database",
            aliases=["es", "搜索引擎"],
        )
    )

    # ------------------ Ollama ------------------
    # Linux tgz 解压为 usr/bin/ollama；macOS zip 为 Ollama.app；Windows zip 解压即用
    components.append(
        Component(
            key="ollama",
            display_name="Ollama",
            env_var=None,
            # Linux/Windows：bin/ollama；macOS：Ollama.app/Contents/Resources/ollama
            path_subdir="bin",
            exec_name="ollama",
            version_args=["--version"],
            versions=[_tgz_cv(v, _ollama_urls(v)) for v in ("0.12.9", "0.3.14")],
            category="ai",
            aliases=["大模型", "llm", "本地模型"],
            extra_bin_dirs=["Contents/Resources", "Contents/MacOS"],
        )
    )

    # ------------------ Hadoop ------------------
    components.append(
        Component(
            key="hadoop",
            display_name="Apache Hadoop",
            env_var="HADOOP_HOME",
            path_subdir="bin",
            exec_name="hadoop",
            version_args=["version"],
            versions=[_tgz_cv(v, _hadoop_urls(v)) for v in ("3.5.0", "3.4.3", "3.3.6")],
            category="bigdata",
            aliases=["hdfs", "mapreduce"],
        )
    )

    # ------------------ ZooKeeper ------------------
    components.append(
        Component(
            key="zookeeper",
            display_name="Apache ZooKeeper",
            env_var="ZOOKEEPER_HOME",
            path_subdir="bin",
            exec_name="zkServer",
            version_args=["version"],
            versions=[_tgz_cv(v, _zookeeper_urls(v)) for v in ("3.9.6", "3.8.4")],
            category="bigdata",
            aliases=["zk"],
        )
    )

    # ------------------ Hive ------------------
    components.append(
        Component(
            key="hive",
            display_name="Apache Hive",
            env_var="HIVE_HOME",
            path_subdir="bin",
            # 用 beeline --version 探测（hive CLI 对 --version 的支持不稳定）
            exec_name="beeline",
            version_args=["--version"],
            versions=[_tgz_cv(v, _hive_urls(v)) for v in ("4.2.1", "4.0.1", "3.1.3")],
            category="bigdata",
        )
    )

    # ------------------ HBase ------------------
    components.append(
        Component(
            key="hbase",
            display_name="Apache HBase",
            env_var="HBASE_HOME",
            path_subdir="bin",
            exec_name="hbase",
            version_args=["version"],
            versions=[_tgz_cv(v, _hbase_urls(v)) for v in ("3.0.0", "2.6.7", "2.6.0")],
            category="bigdata",
        )
    )

    # ------------------ Spark ------------------
    components.append(
        Component(
            key="spark",
            display_name="Apache Spark",
            env_var="SPARK_HOME",
            path_subdir="bin",
            exec_name="spark-submit",
            version_args=["--version"],
            versions=[_tgz_cv(v, _spark_urls(v)) for v in ("4.2.0", "4.0.0", "3.5.3")],
            category="bigdata",
        )
    )

    # ------------------ Flink ------------------
    components.append(
        Component(
            key="flink",
            display_name="Apache Flink",
            env_var="FLINK_HOME",
            path_subdir="bin",
            exec_name="flink",
            version_args=["--version"],
            versions=[_tgz_cv(v, _flink_urls(v)) for v in ("2.3.0", "1.20.0", "1.18.1")],
            category="bigdata",
        )
    )

    # ------------------ Kafka ------------------
    components.append(
        Component(
            key="kafka",
            display_name="Apache Kafka",
            env_var="KAFKA_HOME",
            path_subdir="bin",
            exec_name="kafka-topics",
            version_args=["--version"],
            versions=[_tgz_cv(v, _kafka_urls(v)) for v in ("4.3.1", "3.9.0", "3.8.1")],
            category="bigdata",
        )
    )

    # ------------------ Claude Code（AI） ------------------
    # 通过本机 npm 便携安装到独立目录（前置：已安装 Node.js）
    components.append(
        Component(
            key="claude-code",
            display_name="Claude Code",
            env_var="CLAUDE_CODE_HOME",
            path_subdir="node_modules/.bin",
            exec_name="claude",
            version_args=["--version"],
            versions=[
                ComponentVersion(v, {"Windows": "npm", "Darwin": "npm", "Linux": "npm"})
                for v in ("2.1.292", "2.1.291", "2.1.290")
            ],
            category="ai",
            aliases=["claude", "cc", "anthropic"],
            npm_package="@anthropic-ai/claude-code",
            extra_bin_dirs=["node_modules/.bin"],
        )
    )

    # ------------------ CC-Switch（AI） ------------------
    # Windows 便携 zip（cc-switch.exe）/ macOS「CC Switch.app」/ Linux AppImage
    components.append(
        Component(
            key="cc-switch",
            display_name="CC-Switch",
            env_var=None,
            path_subdir="",  # Linux AppImage 重命名后放在安装目录根
            exec_name="cc-switch",
            version_args=["--version"],
            versions=[
                ComponentVersion(
                    v,
                    _ccswitch_urls(v),
                    {"Windows": "zip", "Darwin": "tar.gz", "Linux": "bin"},
                )
                for v in ("4.0.4", "4.0.3", "4.0.2")
            ],
            category="ai",
            aliases=["ccswitch", "cc switch", "供应商切换", "镜像源切换"],
            extra_bin_dirs=["CC Switch.app/Contents/MacOS", ""],
            raw_bin_name="cc-switch",
        )
    )

    # ------------------ PostgreSQL（数据库） ------------------
    # Win/macOS 用 EDB 免安装 zip；Linux 用官方源码自动编译（不依赖 readline/zlib）
    pg_after_extract = None
    if CURRENT_OS == "Linux":
        pg_after_extract = [
            ["./configure", "--prefix={home}", "--without-readline", "--without-zlib"],
            ["make", "-j4"],
            ["make", "install"],
        ]
    components.append(
        Component(
            key="postgresql",
            display_name="PostgreSQL",
            env_var="PG_HOME",
            path_subdir="bin",
            exec_name="psql",
            version_args=["--version"],
            versions=[
                ComponentVersion(
                    v,
                    _pg_urls(v),
                    {"Windows": "zip", "Darwin": "zip", "Linux": "tar.gz"},
                )
                for v in ("18.4", "17.9", "16.13")
            ],
            category="database",
            aliases=["pg", "postgres", "postgre"],
            # Linux 源码 make install 后 bin 在根下；Win/macOS EDB 包带一层 pgsql/ 根目录
            extra_bin_dirs=["pgsql/bin"],
            after_extract=pg_after_extract,
            post_notes=[
                "本工具只完成下载/编译与环境变量配置；初始化数据库请执行 initdb -D <数据目录>，再用 pg_ctl 启动。",
            ] if CURRENT_OS == "Linux" else [
                "本工具只完成下载与环境变量配置；初始化数据库请执行 initdb -D <数据目录>，再用 pg_ctl 启动。",
            ],
        )
    )

    # ------------------ openGauss（信创数据库，仅 Linux） ------------------
    # Lite 外层是 install.sh + .bin 载荷；after_extract 把 .bin（标准 bin/lib 布局）解到安装目录
    components.append(
        Component(
            key="opengauss",
            display_name="openGauss",
            env_var="OPENGAUSS_HOME",
            path_subdir="bin",
            exec_name="gsql",
            version_args=["--version"],
            versions=[_tgz_cv(v, _opengauss_urls(v)) for v in ("7.0.0", "6.0.1", "6.0.0")],
            category="database",
            aliases=["高斯", "华为数据库", "gaussdb", "信创"],
            after_extract=[
                ["sh", "-c", "tar -zxf openGauss-Lite-*.bin && rm -f openGauss-Lite-*.bin"]
            ],
            post_notes=[
                "解压解包的是程序本体（bin/gsql 等）；如需初始化单机实例，可在安装目录外层使用官方 install.sh -R <程序目录> -D <数据目录>。",
            ],
        )
    )

    # ------------------ 达梦 DM8（信创数据库） ------------------
    # 官方分发包是 zip 套 ISO；本工具完成下载+解出 ISO，安装需挂载后运行镜像内安装器
    dm_label = "2026.07.09" if CURRENT_OS == "Windows" else "2026.07.10"
    components.append(
        Component(
            key="dameng",
            display_name="达梦数据库 DM8",
            env_var=None,
            path_subdir="",
            exec_name=None,
            versions=[
                ComponentVersion(
                    dm_label,
                    _dameng_default_urls(),
                    {"Windows": "zip", "Linux": "zip"},
                )
            ],
            category="database",
            aliases=["达梦", "dm", "dameng", "信创"],
            post_notes=[
                "解压后得到的是 ISO 镜像：Windows 请双击挂载后运行安装程序；Linux 请 mount -o loop <ISO> 后执行 ./DMInstall.bin -i。",
                "如需静默安装，可参考达梦官方文档使用 auto_install.xml。",
            ],
        )
    )

    # ------------------ OceanBase（信创数据库，仅 Linux） ------------------
    ob_default_versions = [
        (
            "4.4.2.3",
            "v4.4.2_CE_BP3",
            "oceanbase-ce-4.4.2.3-103000052026090811.el7.x86_64.rpm",
        ),
        (
            "4.3.5.6",
            "v4.3.5_CE_BP6",
            "oceanbase-ce-4.3.5.6-106000012026040916.el7.x86_64.rpm",
        ),
    ]
    ob_versions: List[ComponentVersion] = []
    for v, tag, rpm_name in ob_default_versions:
        url = f"https://github.com/oceanbase/oceanbase/releases/download/{tag}/{rpm_name}"
        ob_versions.append(ComponentVersion(
            version=v,
            url_map={"Windows": "", "Darwin": "", "Linux": url},
            archive_map={"Linux": "rpm"},
        ))
    components.append(
        Component(
            key="oceanbase",
            display_name="OceanBase",
            env_var="OB_HOME",
            path_subdir="bin",
            exec_name="observer",
            version_args=["-V"],
            versions=ob_versions,
            category="database",
            aliases=["ob", "蚂蚁数据库", "信创"],
            extra_bin_dirs=["home/admin/oceanbase/bin", "home/admin/oceanbase/lib"],
            post_notes=[
                "RPM 已便携解包到 home/admin/oceanbase；observer 启动需配置文件与数据目录，请参照 OceanBase 官方文档。",
            ],
        )
    )

    # ------------------ MariaDB（MySQL 社区分支） ------------------
    components.append(
        Component(
            key="mariadb",
            display_name="MariaDB",
            env_var="MARIADB_HOME",
            path_subdir="bin",
            exec_name="mariadb",
            version_args=["--version"],
            versions=[
                ComponentVersion(
                    v,
                    _mariadb_urls(v),
                    {"Windows": "zip", "Linux": "tar.gz"},
                )
                for v in ("12.3.3", "11.4.13", "10.11.13")
            ],
            category="database",
            aliases=["maria", "mariadb", "mysql分支", "mysql 分支"],
            post_notes=[
                "首次使用请初始化数据目录：scripts/mariadb-install-db --datadir=<数据目录>，"
                "再用 bin/mariadbd-safe 启动（生产环境建议使用包内 systemd 单元）。",
            ] if CURRENT_OS == "Linux" else [
                "首次使用请以管理员身份运行 bin\\mariadb-install-db.exe 初始化数据目录；"
                "启动可执行 bin\\mariadbd.exe，或注册服务：mariadbd.exe --install。",
            ],
        )
    )

    # ------------------ SQL Server 2025 Express（仅 Windows 引导） ------------------
    # 微软只提供在线引导程序（fwlink，约 4.5MB），无便携包；本工具下载 exe 后请按向导安装
    components.append(
        Component(
            key="sqlserver",
            display_name="SQL Server 2025 Express",
            env_var=None,
            path_subdir="",
            exec_name=None,
            versions=[
                ComponentVersion(
                    "2025 Express",
                    {
                        "Windows": "https://go.microsoft.com/fwlink/p/?linkid=2216019&clcid=0x409",
                        "Darwin": "",
                        "Linux": "",
                    },
                    {"Windows": "exe"},
                )
            ],
            category="database",
            aliases=["mssql", "sqlserver", "sql server", "微软数据库"],
            raw_bin_name="SQL2025-SSEI-Expr.exe",
            post_notes=[
                "下载的是在线引导程序 SQL2025-SSEI-Expr.exe：请双击运行，按向导选择安装类型"
                "（基本 / 自定义 / 仅下载介质），安装包本体在引导过程中在线拉取。",
                "Linux 与 macOS 请使用 Docker 镜像 mcr.microsoft.com/mssql/server 运行。",
            ],
        )
    )

    # ------------------ TiDB（分布式数据库，仅 Linux） ------------------
    # tiup-mirrors 直链；tar 内仅一个 tidb-server，学习可用内嵌 unistore 单机启动
    tidb_arch = "arm64" if IS_ARM else "amd64"
    components.append(
        Component(
            key="tidb",
            display_name="TiDB",
            env_var="TIDB_HOME",
            path_subdir="",
            exec_name="tidb-server",
            version_args=["-V"],
            versions=[
                ComponentVersion(
                    v,
                    {"Windows": "", "Darwin": "",
                     "Linux": f"https://tiup-mirrors.pingcap.com/tidb-v{v}-linux-{tidb_arch}.tar.gz"},
                    {"Linux": "tar.gz"},
                )
                for v in ("8.5.6", "8.1.2", "7.5.7")
            ],
            category="database",
            aliases=["tidb", "pingcap", "分布式数据库"],
            post_notes=[
                "包内仅 tidb-server 一个可执行文件：学习测试可执行 "
                "tidb-server -P 4000 --store=unistore --path=<数据目录> 启动内嵌存储单机实例。",
                "生产集群还需 PD、TiKV 等组件（tiup-mirrors 上同名 pd-/tikv- 包），"
                "建议按官方文档使用 tiup 部署。",
            ],
        )
    )

    # ------------------ 人大金仓 KingbaseES（仅 Linux 便携包） ------------------
    # 主流 V9R1C10 是需申请的 GUI ISO；官网另发布免登录 kingbase-server 便携 tar（金融版构建，
    # 自带 license.dat）。OSS Referer 防盗链：组件声明 download_headers 下载时自动带 Referer。
    kb_oss = "https://kingbase.oss-cn-beijing.aliyuncs.com/upload/KESV9-baseline/Medition/waihuijyzx"
    kb_default = [
        (
            "V009R003C011B0003PS008",
            "V9R3C11 PS008",
            f"{kb_oss}/V9R3C11/V009R003C011B0003PS008/"
            "kingbase-server-V009R003C011B0003PS008-linux-x86_64.tar",
        ),
        (
            "V008R006C008B0015PS008",
            "V8R6C8 PS008",
            f"{kb_oss}/V8R6C8B15/V008R006C008B0015PS008/"
            "kingbase-server-V008R006C008B0015PS008-linux-x86_64.tar",
        ),
    ]
    components.append(
        Component(
            key="kingbase",
            display_name="人大金仓 KingbaseES",
            env_var="KINGBASE_HOME",
            path_subdir="bin",
            exec_name="ksql",
            version_args=["--version"],
            versions=[
                ComponentVersion(
                    build,
                    {"Windows": "", "Darwin": "", "Linux": url},
                    {"Linux": "tar"},
                    display_label=label,
                )
                for build, label, url in kb_default
            ],
            category="database",
            aliases=["金仓", "kingbase", "kingbasees", "kes", "信创"],
            download_headers={"Referer": "https://www.kingbase.com.cn/"},
            post_notes=[
                "tar 解包为标准 bin/lib 布局（bin/ 下自带 license.dat）；初始化："
                "bin/initdb -D <数据目录> -U system，再 bin/sys_ctl start -D <数据目录> 启动。",
                "Windows 需使用官网 GUI 安装 ISO（kingbase.com.cn，需申请）。",
            ],
        )
    )

    # ------------------ 崖山 YashanDB（仅 Linux） ------------------
    # 外层 tar：bin/yasboot + depends/ + install.sh + 内层 database-*.tar.gz
    yas_default = "23.4.1.109"
    components.append(
        Component(
            key="yashandb",
            display_name="崖山数据库 YashanDB",
            env_var="YASHANDB_HOME",
            path_subdir="bin",
            exec_name="yasql",
            version_args=["--version"],
            versions=[
                ComponentVersion(
                    yas_default,
                    {"Windows": "", "Darwin": "",
                     "Linux": "https://yashandb-website.oss-cn-shenzhen.aliyuncs.com/"
                              "2026/03/06/1772763539649-g3Hyashandb-23.4.1.109-linux-x86_64%20(2).tar.gz"},
                    {"Linux": "tar.gz"},
                )
            ],
            category="database",
            aliases=["崖山", "yashan", "yashandb", "信创"],
            after_extract=[
                ["sh", "-c", "tar -zxf database-*.tar.gz && rm -f database-*.tar.gz"]
            ],
            post_notes=[
                "初始化：在安装目录执行 ./install.sh（等价 yasboot init，交互输入数据目录与口令；"
                "要求 /proc/sys/kernel/pid_max ≥ 32769）。",
                "启动：bin/yasboot cluster start -d <数据目录>；连接："
                "bin/yasql sys/<口令>@127.0.0.1:1688。",
            ],
        )
    )

    return components


# ---------------------------------------------------------------------------
# 下载线程
# ---------------------------------------------------------------------------
class DownloadWorker(QThread):
    """使用 requests 流式下载文件的后台线程。"""

    progress = Signal(int, int)  # (downloaded_bytes, total_bytes)
    log = Signal(str, str)  # (level, message)  level in {"info","warn","error","ok"}
    finished_ok = Signal(str)  # 保存的本地文件绝对路径
    finished_fail = Signal(str)  # 错误信息

    def __init__(self, url: str, dest: Path, headers: Optional[Dict[str, str]] = None,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.url = url
        self.dest = dest
        self.headers = headers or None
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:  # noqa: D401
        try:
            self.log.emit("info", f"开始下载：{self.url}")
            ensure_dir(self.dest.parent)
            with requests.get(self.url, stream=True, timeout=30, allow_redirects=True,
                              headers=self.headers) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                downloaded = 0
                tmp = self.dest.with_suffix(self.dest.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if self._cancel:
                            self.log.emit("warn", "已取消下载。")
                            f.close()
                            tmp.unlink(missing_ok=True)
                            self.finished_fail.emit("用户取消")
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            self.progress.emit(downloaded, total)
                tmp.replace(self.dest)
            self.log.emit("ok", f"下载完成：{self.dest} ({human_size(self.dest.stat().st_size)})")
            self.finished_ok.emit(str(self.dest))
        except Exception as exc:  # pragma: no cover
            self.log.emit("error", f"下载失败：{exc}")
            self.finished_fail.emit(str(exc))


class CommandWorker(QThread):
    """在后台执行外部命令（如 npm 便携安装），并把输出实时转发到日志。"""

    log = Signal(str, str)  # (level, message)
    finished_ok = Signal(str)
    finished_fail = Signal(str)

    def __init__(self, cmd: List[str], cwd: Optional[Path] = None,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.cmd = cmd
        self.cwd = str(cwd) if cwd else None
        self._proc: Optional[subprocess.Popen] = None
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True
        if self._proc is not None and self._proc.poll() is None:
            try:
                if CURRENT_OS == "Windows":
                    self._proc.terminate()
                else:
                    import signal
                    os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except Exception:
                pass

    def run(self) -> None:  # noqa: D401
        try:
            self.log.emit("info", f"执行：{' '.join(self.cmd)}（目录：{self.cwd or os.getcwd()}）")
            kwargs = dict(
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                encoding="utf-8",
                errors="replace",
            )
            if CURRENT_OS != "Windows":
                kwargs["start_new_session"] = True
            self._proc = subprocess.Popen(self.cmd, **kwargs)
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                text = line.rstrip()
                if text:
                    self.log.emit("info", text[:500])
            code = self._proc.wait()
            if self._cancel:
                self.finished_fail.emit("用户取消")
                return
            if code != 0:
                self.finished_fail.emit(f"命令返回非零退出码：{code}")
                return
            self.finished_ok.emit("")
        except Exception as exc:  # pragma: no cover
            self.log.emit("error", f"命令执行失败：{exc}")
            self.finished_fail.emit(str(exc))


# ---------------------------------------------------------------------------
# 环境变量处理
# ---------------------------------------------------------------------------
class EnvManager:
    """跨平台环境变量管理器。"""

    @staticmethod
    def get(name: str) -> Optional[str]:
        return os.environ.get(name)

    @staticmethod
    def is_valid_home(path: str, exec_name: str) -> bool:
        """判断 XXX_HOME 是否有效——检查 bin 目录下是否存在可执行文件。"""
        if not path:
            return False
        p = Path(path)
        bin_dir = p / "bin"
        exe = bin_dir / (exec_name + (".exe" if CURRENT_OS == "Windows" else ""))
        return exe.exists()

    @staticmethod
    def set_windows_user_env(name: str, value: str) -> None:
        """在 Windows 上使用 setx 永久写入用户环境变量。"""
        # setx 会截断超过 1024 字符的 PATH，这里额外用 winreg 直接写注册表
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS
            ) as key:
                reg_type = winreg.REG_EXPAND_SZ if "%" in value else winreg.REG_SZ
                winreg.SetValueEx(key, name, 0, reg_type, value)
            # 通知系统刷新
            subprocess.run(
                ["setx", name, value],
                check=False,
                shell=False,
                capture_output=True,
            )
        except Exception as exc:
            raise RuntimeError(f"写入 Windows 环境变量失败：{exc}")

    @staticmethod
    def append_windows_path(entry: str) -> None:
        """把 entry 追加到 Windows 用户 PATH。"""
        import winreg  # type: ignore

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS
        ) as key:
            try:
                current, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current = ""
        parts = [p for p in current.split(";") if p]
        if entry in parts:
            return
        parts.append(entry)
        EnvManager.set_windows_user_env("Path", ";".join(parts))

    @staticmethod
    def _shell_rc_file() -> Path:
        """选择 macOS / Linux 上要写入的 shell 配置文件。"""
        home = Path.home()
        shell = os.environ.get("SHELL", "")
        if shell.endswith("zsh"):
            return home / ".zshrc"
        if shell.endswith("bash"):
            # macOS 上 bash 更常读 ~/.bash_profile
            return home / (".bash_profile" if CURRENT_OS == "Darwin" else ".bashrc")
        return home / ".profile"

    @staticmethod
    def set_unix_env(name: str, value: str) -> Path:
        """在 UNIX 系统上，把 export 语句写入 shell 配置文件；返回被修改的文件路径。"""
        rc = EnvManager._shell_rc_file()
        # 标记保持旧品牌名 env-auto-setup：改名 MuRig 后老用户 rc 文件里的块仍需被识别和幂等更新
        marker_begin = f"# >>> env-auto-setup:{name} >>>"
        marker_end = f"# <<< env-auto-setup:{name} <<<"
        new_block = f'{marker_begin}\nexport {name}="{value}"\n{marker_end}\n'

        text = rc.read_text(encoding="utf-8") if rc.exists() else ""
        if marker_begin in text and marker_end in text:
            pre, rest = text.split(marker_begin, 1)
            _, post = rest.split(marker_end, 1)
            new_text = pre + new_block + post
        else:
            sep = "" if text.endswith("\n") or text == "" else "\n"
            new_text = text + sep + "\n" + new_block
        rc.write_text(new_text, encoding="utf-8")
        return rc

    @staticmethod
    def append_unix_path(entry: str) -> Path:
        """把 entry 追加到 PATH。"""
        rc = EnvManager._shell_rc_file()
        marker_begin = f"# >>> env-auto-setup:PATH:{entry} >>>"
        marker_end = f"# <<< env-auto-setup:PATH:{entry} <<<"
        line = f'{marker_begin}\nexport PATH="{entry}:$PATH"\n{marker_end}\n'
        text = rc.read_text(encoding="utf-8") if rc.exists() else ""
        if marker_begin in text:
            return rc
        sep = "" if text.endswith("\n") or text == "" else "\n"
        rc.write_text(text + sep + "\n" + line, encoding="utf-8")
        return rc


# ---------------------------------------------------------------------------
# 归档解压
# ---------------------------------------------------------------------------
def extract_archive(archive: Path, extract_to: Path) -> Path:
    """解压归档，返回解压后（通常包含一个根目录）的根路径。"""
    ensure_dir(extract_to)
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(extract_to)
    elif name.endswith(".tar.gz") or name.endswith(".tgz"):
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(extract_to)
    elif name.endswith(".tar.xz"):
        with tarfile.open(archive, "r:xz") as tf:
            tf.extractall(extract_to)
    elif name.endswith(".tar"):
        # 后缀是 .tar 但可能实为 gzip 压缩（KingbaseES 便携包即如此）；
        # r:* 按魔术字节自动识别压缩格式，真未压缩 tar 也兼容
        with tarfile.open(archive, "r:*") as tf:
            tf.extractall(extract_to)
    else:
        raise RuntimeError(f"未知的归档类型：{archive.name}")

    entries = [p for p in extract_to.iterdir() if p.is_dir()]
    if len(entries) == 1:
        return entries[0]
    return extract_to


def _rpm_header_info(data: bytes):
    """解析 RPM 的 lead + signature header + immutable header。

    返回 (payload 起始偏移, payload 压缩器, 格式)。仅解析 header 索引区。
    索引项为 16 字节：tag / type / offset / count。
    """
    def one_header(off: int):
        if data[off:off + 3] != b"\x8e\xad\xe8":
            raise RuntimeError("不是有效的 RPM 包（header magic 不匹配）")
        count = int.from_bytes(data[off + 8:off + 12], "big")
        dbytes = int.from_bytes(data[off + 12:off + 16], "big")
        tags: Dict[int, tuple] = {}
        idx = off + 16
        for _ in range(count):
            tag, typ, noff, cnt = (
                int.from_bytes(data[idx:idx + 4], "big"),
                int.from_bytes(data[idx + 4:idx + 8], "big"),
                int.from_bytes(data[idx + 8:idx + 12], "big"),
                int.from_bytes(data[idx + 12:idx + 16], "big"),
            )
            tags[tag] = (typ, noff, cnt)
            idx += 16
        return tags, idx, dbytes

    # lead 固定 96 字节
    _sig_tags, sig_store, sig_db = one_header(96)
    sig_end = sig_store + ((sig_db + 7) // 8 * 8)
    hdr_tags, hdr_store, hdr_db = one_header(sig_end)

    def header_string(tag: int) -> str:
        _, off, _ = hdr_tags[tag]
        end = data.index(b"\x00", hdr_store + off)
        return data[hdr_store + off:end].decode()

    # immutable store 后直接衔接 payload（尾部不补齐；8 字节对齐只用于两个 header 之间）
    payload_off = hdr_store + hdr_db
    return payload_off, header_string(1125), header_string(1124)


def extract_rpm(rpm: Path, extract_to: Path) -> Path:
    """把 RPM（cpio + xz/gzip/zstd）解包到目录，返回 extract_to。

    不依赖系统 rpm2cpio；xz/gzip 走标准库，zstd 需要系统 zstd 命令。
    """
    import lzma
    import gzip

    ensure_dir(extract_to)
    with open(rpm, "rb") as f:
        head = f.read(512 * 1024)
        payload_off, compressor, payload_fmt = _rpm_header_info(head)
        f.seek(payload_off)

        cpio_tmp = extract_to.parent / f".{rpm.stem}.cpio"
        with open(cpio_tmp, "wb") as out:
            if compressor in ("xz", "lzma"):
                dec = lzma.LZMADecompressor()
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(dec.decompress(chunk))
            elif compressor == "gzip":
                dec = gzip.GzipFile(fileobj=f)
                shutil.copyfileobj(dec, out)
            elif compressor == "zstd":
                zstd = shutil.which("zstd")
                if not zstd:
                    raise RuntimeError("该 RPM 使用 zstd 压缩，请先安装 zstd（brew install zstd / apt install zstd）")
                proc = subprocess.Popen(
                    [zstd, "-dc", "-"], stdin=subprocess.PIPE, stdout=out,
                )
                try:
                    shutil.copyfileobj(f, proc.stdin)
                finally:
                    if proc.stdin:
                        proc.stdin.close()
                if proc.wait() != 0:
                    raise RuntimeError("zstd 解压失败")
            else:
                raise RuntimeError(f"暂不支持的 RPM 压缩格式：{compressor}（payload={payload_fmt}）")

    _extract_cpio_newc(cpio_tmp, extract_to)
    cpio_tmp.unlink(missing_ok=True)
    return extract_to


def _extract_cpio_newc(cpio_file: Path, dest: Path) -> None:
    """流式解析 cpio newc（magic 070701/070702）归档并提取文件。"""
    with open(cpio_file, "rb") as data:
        while True:
            h = data.read(110)
            if len(h) < 110 or h[:6] not in (b"070701", b"070702"):
                break
            filesize = int(h[54:62], 16)
            namesize = int(h[94:102], 16)
            mode = int(h[14:22], 16)
            raw_name = data.read(namesize)
            name = raw_name[:-1].decode("utf-8", "replace")
            # 头部(110) + 名称整体按 4 字节对齐
            data.seek((-(110 + namesize)) % 4, 1)

            if name == "TRAILER!!!":
                break
            # 规范掉 ./ 与 / 前缀（RPM 内名称常见 "./usr/..."）
            rel = name
            while rel.startswith("./"):
                rel = rel[2:]
            rel = rel.lstrip("/")
            ftype = mode & 0o170000
            target = dest / rel if rel else None

            if target is not None and ftype == 0o040000:  # 目录
                target.mkdir(parents=True, exist_ok=True)
                data.seek((-filesize) % 4, 1)
            elif target is not None and ftype == 0o120000:  # 软链接
                link = data.read(filesize).decode("utf-8", "replace")
                data.seek((-filesize) % 4, 1)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink() or target.exists():
                    target.unlink()
                target.symlink_to(link)
            elif target is not None and ftype == 0o100000:  # 普通文件
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "wb") as out:
                    remaining = filesize
                    while remaining > 0:
                        chunk = data.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        out.write(chunk)
                        remaining -= len(chunk)
                try:
                    target.chmod(mode & 0o777)
                except OSError:
                    pass
                data.seek((-filesize) % 4, 1)
            else:
                # 其它类型（设备/fifo 等）跳过数据体
                data.seek(filesize + ((-filesize) % 4), 1)


# ---------------------------------------------------------------------------
# UI 组件：可搜索下拉框
# ---------------------------------------------------------------------------
class SearchableComboBox(QComboBox):
    """支持关键字过滤的下拉框。

    交互设计：
    - 点击输入框任意位置 → 弹出下拉列表（默认显示全部）
    - 输入关键字 → 实时过滤下拉列表中的项
    - 点击某项即选中（也可按回车 / 上下键选择）
    - 无效输入 → 失焦时回滚到上一次选中的值
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)  # 用户输入不添加到列表
        self.lineEdit().setPlaceholderText("点击选择或输入关键字…")

        # 自定义下拉箭头 —— 用 QLabel 显示 unicode 字符，避免 CSS border-hack 渲染问题
        # WA_TransparentForMouseEvents 使鼠标事件穿透到底层 QComboBox drop-down 区域，
        # 让 Qt 自己处理 toggle（点击展开、再次点击关闭），我们不干预。
        self._arrow_label = QLabel("▾", self)
        self._arrow_label.setObjectName("comboArrow")
        self._arrow_label.setAlignment(Qt.AlignCenter)
        self._arrow_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._arrow_label.setFixedWidth(28)

        # 在 lineEdit 上安装 event filter：点击文本区时也弹出下拉
        self.lineEdit().installEventFilter(self)

        # completer：让 QCompleter 也做 contains 匹配（无所谓，主要靠 view 过滤）
        completer = QCompleter(self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        completer.setModel(self.model())
        # 不使用 completer 的独立 popup，直接使用 combo 自带 view，避免视觉重叠
        self.setCompleter(None)

        # 记录当前有效选中项
        self._committed_text: str = ""

        # 连接信号
        self.currentIndexChanged.connect(self._on_index_changed)
        self.lineEdit().textEdited.connect(self._on_text_edited)
        self.lineEdit().editingFinished.connect(self._restore_if_invalid)

    # ------------------------------------------------------------------
    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        # 让箭头 label 始终贴在右侧
        w = self._arrow_label.width()
        self._arrow_label.setGeometry(self.width() - w - 2, 0, w, self.height())

    # ------------------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:
        """点击输入框任何位置 → 弹出下拉。

        直接在 MousePress 阶段接管事件（return True），不让 QLineEdit 后续
        的 press/release 处理进入 QComboBox 内部的 toggle 逻辑 —— 那会导致
        我们刚弹出的 popup 被立即隐藏。
        """
        if obj is self.lineEdit() and event.type() == QEvent.MouseButtonPress:
            self.lineEdit().setFocus()
            if self.view().isVisible():
                self.hidePopup()
            else:
                self.showPopup()
            return True  # 吞掉事件，QLineEdit 不再处理
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    def focusInEvent(self, e) -> None:
        super().focusInEvent(e)
        # 全选文本，方便直接输入替换
        self.lineEdit().selectAll()

    # ------------------------------------------------------------------
    def showPopup(self) -> None:  # noqa: D401
        """展开前先按当前输入过滤，空输入则展示全部。"""
        text = self.lineEdit().text().strip()
        if not text or text == self._committed_text:
            self._set_all_items_visible()
        else:
            self._filter_items(text)
        self._arrow_label.setText("▴")
        super().showPopup()

    # ------------------------------------------------------------------
    def hidePopup(self) -> None:  # noqa: D401
        self._arrow_label.setText("▾")
        super().hidePopup()

    # ------------------------------------------------------------------
    def _on_text_edited(self, text: str) -> None:
        """用户在输入框中键入时：实时过滤 + 展开下拉。"""
        # 展开下拉（若尚未展开）
        if not self.view().isVisible():
            super().showPopup()
        # 过滤
        keyword = text.strip()
        if not keyword:
            self._set_all_items_visible()
        else:
            self._filter_items(keyword)

    # ------------------------------------------------------------------
    def _filter_items(self, keyword: str) -> None:
        keyword = keyword.lower()
        view = self.view()
        first_visible = -1
        for i in range(self.count()):
            visible = keyword in self.itemText(i).lower()
            view.setRowHidden(i, not visible)
            if visible and first_visible < 0:
                first_visible = i
        # 把第一条匹配项高亮，方便回车直接选中
        if first_visible >= 0:
            view.setCurrentIndex(self.model().index(first_visible, 0))

    def _set_all_items_visible(self) -> None:
        view = self.view()
        for i in range(self.count()):
            view.setRowHidden(i, False)

    # ------------------------------------------------------------------
    def _on_index_changed(self, idx: int) -> None:
        if idx >= 0:
            self._committed_text = self.itemText(idx)

    def _restore_if_invalid(self) -> None:
        """失焦时若输入内容并不精确匹配某项，则回滚到上一次选中值。"""
        text = self.lineEdit().text().strip()
        for i in range(self.count()):
            if self.itemText(i).lower() == text.lower():
                self.setCurrentIndex(i)
                return
        if self._committed_text:
            self.lineEdit().setText(self._committed_text)

    # ------------------------------------------------------------------
    def repopulate(self, items: List[str], preferred: Optional[str] = None) -> None:
        """清空后重新加载列表；尽量保持之前选中值。"""
        prev = preferred or self.currentText()
        self.blockSignals(True)
        self.clear()
        self.addItems(items)
        idx = self.findText(prev) if prev else -1
        self.setCurrentIndex(idx if idx >= 0 else 0)
        self.blockSignals(False)
        if self.count():
            self._committed_text = self.currentText()
        self._set_all_items_visible()


# ---------------------------------------------------------------------------
# UI 组件：卡片
# ---------------------------------------------------------------------------
class ComponentCard(QFrame):
    """展示一个组件的卡片。"""

    request_log = Signal(str, str)

    def __init__(self, component: Component, log_cb: Callable[[str, str], None], parent=None) -> None:
        super().__init__(parent)
        self.component = component
        self.log_cb = log_cb
        self.worker: Optional[DownloadWorker] = None
        self.cmd_worker: Optional[CommandWorker] = None
        self._extracted_path: Optional[Path] = None

        self.setObjectName("card")
        self.setFrameShape(QFrame.NoFrame)

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)

        self._build_ui()
        self._detect_status()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # 顶部：名称 & 状态
        top = QHBoxLayout()
        top.setSpacing(10)
        title = QLabel(self.component.display_name)
        title.setObjectName("cardTitle")
        title.setFont(QFont("", 14, QFont.Bold))
        top.addWidget(title)

        self.status_label = QLabel("检测中…")
        self.status_label.setObjectName("statusLabel")
        top.addWidget(self.status_label)
        top.addStretch(1)
        root.addLayout(top)

        # 中部：版本选择 + 按钮
        mid = QHBoxLayout()
        mid.setSpacing(10)
        version_label = QLabel("版本")
        version_label.setObjectName("fieldLabel")
        version_label.setFixedWidth(36)
        mid.addWidget(version_label)

        self.version_combo = SearchableComboBox()
        self.version_combo.setObjectName("versionCombo")
        self.version_combo.setCursor(QCursor(Qt.PointingHandCursor))
        self._reload_combo_items()
        # 固定宽度，避免抢占按钮空间
        self.version_combo.setFixedWidth(220)
        self.version_combo.setFixedHeight(34)
        self.version_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        mid.addWidget(self.version_combo)

        mid.addSpacing(8)

        self.btn_install = QPushButton("安装" if self.component.npm_package else "下载并安装")
        self.btn_install.setObjectName("primaryBtn")
        self.btn_install.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_install.setFixedHeight(34)
        self.btn_install.clicked.connect(self.on_install_clicked)
        mid.addWidget(self.btn_install)

        self.btn_configure = QPushButton("配置环境变量")
        self.btn_configure.setObjectName("secondaryBtn")
        self.btn_configure.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_configure.setFixedHeight(34)
        self.btn_configure.clicked.connect(self.on_configure_clicked)
        mid.addWidget(self.btn_configure)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("dangerBtn")
        self.btn_cancel.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setVisible(False)  # 默认隐藏；开始下载时才显示
        self.btn_cancel.clicked.connect(self.on_cancel_clicked)
        mid.addWidget(self.btn_cancel)

        mid.addStretch(1)  # 右侧留空，避免下拉框被拉伸
        root.addLayout(mid)

        # 底部：进度条
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(True)
        self.progress.setValue(0)
        root.addWidget(self.progress)

    # ------------------------------------------------------------------
    def _log(self, level: str, msg: str) -> None:
        self.log_cb(level, f"[{self.component.display_name}] {msg}")

    # ------------------------------------------------------------------
    def _detect_status(self) -> None:
        """检测该组件当前是否已安装、已配置。

        - 若系统 PATH 或 XXX_HOME 已能找到可执行文件，则视为「已配置」，禁用
          「仅配置环境变量」按钮，避免重复写入。
        - 若本地已解压但未配置，则允许点击「仅配置环境变量」。
        - 若未安装，两个按钮均可用。
        """
        result = self.component.detect()
        if result.installed:
            ver = result.version_text or "未知版本"
            where = result.source or "系统"
            self.status_label.setText(f"✓ 已配置（{where}） · {ver}")
            self.status_label.setStyleSheet(
                "color:#2e7d32;font-weight:600;padding:2px 8px;"
                "background:#e8f5e9;border-radius:10px;"
            )
            # 已可用 —— 禁用「仅配置环境变量」按钮
            self.btn_configure.setEnabled(False)
            self.btn_configure.setToolTip(
                f"系统已能检测到 {self.component.display_name}"
                f"（{result.exe_path or where}），无需再次配置。"
            )
            return

        # 尝试查找本地已解压目录
        install_root = CONFIG_DIR / self.component.key
        if install_root.exists() and any(
            p for p in install_root.iterdir()
            if p.is_dir() and not p.name.startswith(".") and p.name != "downloads"
        ):
            self.status_label.setText("● 已下载，未配置")
            self.status_label.setStyleSheet(
                "color:#ef6c00;font-weight:600;padding:2px 8px;"
                "background:#fff3e0;border-radius:10px;"
            )
            self.btn_configure.setEnabled(True)
            self.btn_configure.setToolTip("将已下载的版本写入 XXX_HOME 与 PATH")
            return

        self.status_label.setText("○ 未安装")
        self.status_label.setStyleSheet(
            "color:#c62828;font-weight:600;padding:2px 8px;"
            "background:#ffebee;border-radius:10px;"
        )
        self.btn_configure.setEnabled(True)
        self.btn_configure.setToolTip("将已下载的版本写入 XXX_HOME 与 PATH")

    # ------------------------------------------------------------------
    def _display_label(self, cv: ComponentVersion) -> str:
        return getattr(cv, "display_label", None) or cv.version

    def _reload_combo_items(self, preferred: Optional[str] = None) -> None:
        """把 self.component.versions 灌进下拉框。"""
        labels = [self._display_label(v) for v in self.component.versions]
        # 若首次调用（combo 里还没内容），走普通 addItems 路径
        if self.version_combo.count() == 0:
            self.version_combo.blockSignals(True)
            self.version_combo.addItems(labels)
            self.version_combo.setCurrentIndex(0)
            self.version_combo.blockSignals(False)
            self.version_combo._committed_text = self.version_combo.currentText()
            return
        self.version_combo.repopulate(labels, preferred=preferred)

    def set_versions(self, versions: List[ComponentVersion]) -> None:
        """外部（抓取线程）用新版本列表替换现有列表。"""
        if not versions:
            return
        prev_ver = self._current_version().version if self.component.versions else None
        self.component.versions = versions
        preferred_label = None
        if prev_ver:
            for cv in versions:
                if cv.version == prev_ver:
                    preferred_label = self._display_label(cv)
                    break
        self._reload_combo_items(preferred=preferred_label)
        self._log("ok", f"已从官网获取 {len(versions)} 个版本")

    # ------------------------------------------------------------------
    def _current_version(self) -> ComponentVersion:
        """按显示 label 反查真实版本，兼容 SearchableComboBox 的可编辑文本。"""
        text = self.version_combo.currentText().strip()
        for cv in self.component.versions:
            if self._display_label(cv) == text or cv.version == text:
                return cv
        idx = max(0, self.version_combo.currentIndex())
        return self.component.versions[min(idx, len(self.component.versions) - 1)]

    # ------------------------------------------------------------------
    def on_install_clicked(self) -> None:
        cv = self._current_version()

        # npm 便携安装模式（如 Claude Code）：不走下载流程
        if self.component.npm_package:
            self._start_npm_install(cv)
            return

        url = cv.url_for_current()
        if not url:
            self._log("error", f"当前系统 {CURRENT_OS} 无可用下载地址。")
            return

        # 决定下载文件后缀
        if self.component.installer_mode:
            # 从 archive_map 取扩展名（exe / sh），其次从 URL 推断
            ext = cv.archive_map.get(CURRENT_OS, "")
            if not ext:
                if url.endswith(".exe"):
                    ext = "exe"
                elif url.endswith(".sh"):
                    ext = "sh"
                else:
                    ext = "bin"
            suffix = f".{ext}"
        else:
            archive_ext = cv.archive_for_current()
            if archive_ext == "zip":
                suffix = ".zip"
            elif archive_ext == "tar.gz":
                suffix = ".tar.gz"
            elif archive_ext == "tar":
                suffix = ".tar"
            elif archive_ext == "rpm":
                suffix = ".rpm"
            elif archive_ext == "exe":
                suffix = ".exe"
            else:
                # 独立可执行文件（如 AppImage）：保留原始后缀，没有则用 .bin
                suffix = "".join(PurePosixPath(urlparse(url).path).suffixes) or ".bin"

        download_dir = CONFIG_DIR / self.component.key / "downloads"
        ensure_dir(download_dir)
        dest = download_dir / f"{self.component.key}-{cv.version}{suffix}"

        self.progress.setValue(0)
        self.btn_install.setEnabled(False)
        self.btn_configure.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)

        self.worker = DownloadWorker(url, dest, self.component.download_headers)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._log)
        self.worker.finished_ok.connect(lambda p: self._on_download_ok(Path(p), cv))
        self.worker.finished_fail.connect(self._on_download_fail)
        self.worker.start()

    # ------------------------------------------------------------------
    def _on_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            self.progress.setValue(int(downloaded * 100 / total))
            self.progress.setFormat(f"{human_size(downloaded)} / {human_size(total)}")
        else:
            # 未知总长度
            self.progress.setRange(0, 0)
            self.progress.setFormat(f"{human_size(downloaded)}")

    # ------------------------------------------------------------------
    def _on_download_ok(self, path: Path, cv: ComponentVersion) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setVisible(False)

        try:
            target_root = CONFIG_DIR / self.component.key
            ensure_dir(target_root)
            final = self.component.install_dir(cv.version)

            if self.component.installer_mode:
                # 安装器模式：静默执行安装
                self._log("info", "开始运行安装器（静默安装）…")
                if final.exists():
                    shutil.rmtree(final, ignore_errors=True)
                self._run_installer(path, final)
                self._log("ok", f"安装完成：{final}")
            else:
                archive_ext = cv.archive_for_current()
                if archive_ext == "rpm":
                    # RPM：纯 Python 解析（xz/lzma + cpio newc），直接解到 final
                    self._log("info", "开始解包 RPM（cpio）…")
                    if final.exists():
                        shutil.rmtree(final, ignore_errors=True)
                    ensure_dir(final)
                    extract_rpm(path, final)
                    self._log("ok", f"解包完成：{final}")
                elif archive_ext in ("bin", "exe"):
                    # 独立可执行文件（Linux AppImage / Windows 引导程序 .exe）：放入安装目录
                    if final.exists():
                        shutil.rmtree(final, ignore_errors=True)
                    ensure_dir(final)
                    raw_name = self.component.raw_bin_name or path.name
                    raw = final / raw_name
                    shutil.move(str(path), str(raw))
                    try:
                        raw.chmod(0o755)
                    except OSError:
                        pass
                    self._log("ok", f"可执行文件已就绪：{raw}")
                else:
                    self._log("info", "开始解压…")
                    # 解压到临时目录
                    tmp_dir = target_root / f".extract-{cv.version}"
                    if tmp_dir.exists():
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                    ensure_dir(tmp_dir)
                    root = extract_archive(path, tmp_dir)

                    if final.exists():
                        shutil.rmtree(final, ignore_errors=True)
                    shutil.move(str(root), str(final))
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    self._log("ok", f"解压完成：{final}")

            # 源码类组件的编译步骤（如 Redis 执行 make）
            if self.component.after_extract:
                self._run_after_extract(final)

            self._extracted_path = final
            # 自动尝试配置环境变量
            self._configure_env(final)
            for note in self.component.post_notes:
                self._log("warn", note)
        except Exception as exc:
            self._log("error", f"安装/配置失败：{exc}\n{traceback.format_exc()}")
        finally:
            self.btn_install.setEnabled(True)
            self.btn_configure.setEnabled(True)
            # _detect_status 会根据探测结果再决定 btn_configure 是否禁用
            self._detect_status()

    # ------------------------------------------------------------------
    def _run_installer(self, installer_path: Path, target_dir: Path) -> None:
        """静默运行安装器（用于 Miniconda 之类）。"""
        comp = self.component
        args = list(comp.installer_args.get(CURRENT_OS, []))
        ensure_dir(target_dir.parent)

        if CURRENT_OS == "Windows":
            # Windows Miniconda: 参数末尾 /D=path 不允许带引号
            cmd = [str(installer_path)] + args + [f"/D={target_dir}"]
            self._log("info", f"运行：{' '.join(cmd)}")
            proc = subprocess.run(cmd, check=False)
        else:
            # macOS / Linux: bash installer.sh -b -f -p <path>
            os.chmod(installer_path, 0o755)
            cmd = ["bash", str(installer_path)] + args + [str(target_dir)]
            self._log("info", f"运行：{' '.join(cmd)}")
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.stdout:
                self._log("info", proc.stdout.strip()[:500])
            if proc.stderr:
                self._log("warn", proc.stderr.strip()[:500])

        if proc.returncode != 0:
            raise RuntimeError(f"安装器返回非零退出码：{proc.returncode}")

    # ------------------------------------------------------------------
    def _run_after_extract(self, home: Path) -> None:
        """在安装目录内依次执行组件声明的编译/初始化命令（失败只告警，不中断流程）。"""
        for raw_cmd in self.component.after_extract or []:
            # 支持 {home} 占位符（如 ./configure --prefix={home}）
            cmd = [arg.replace("{home}", str(home)) for arg in raw_cmd]
            self._log("info", f"执行：{' '.join(cmd)}（目录：{home}）")
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(home),
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
                if proc.stdout:
                    self._log("info", proc.stdout.strip()[:400])
                if proc.stderr:
                    self._log("info", proc.stderr.strip()[:400])
                if proc.returncode != 0:
                    self._log(
                        "warn",
                        f"命令返回非零退出码 {proc.returncode}，可尝试在 {home} 手动执行。",
                    )
            except Exception as exc:
                self._log("warn", f"命令执行失败：{exc}")

    # ------------------------------------------------------------------
    def _on_download_fail(self, msg: str) -> None:
        self.btn_install.setEnabled(True)
        self.btn_configure.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        if msg and msg != "用户取消":
            QMessageBox.warning(self, "下载失败", f"{self.component.display_name} 下载失败：\n{msg}")

    # ------------------------------------------------------------------
    def _start_npm_install(self, cv: ComponentVersion) -> None:
        """使用本机 npm 把包便携安装到独立目录（不污染全局）。"""
        comp = self.component
        npm = shutil.which("npm.cmd" if CURRENT_OS == "Windows" else "npm") or shutil.which("npm")
        if not npm:
            self._log("error", "未检测到 npm，请先通过本工具安装 Node.js（或自行安装 Node.js）。")
            return
        final = comp.install_dir(cv.version)
        ensure_dir(final)
        spec = f"{comp.npm_package}@{cv.version}"
        args = ["install", "--prefix", str(final), "--no-fund", "--no-audit", spec]
        if CURRENT_OS == "Windows" and npm.lower().endswith((".cmd", ".bat")):
            # .cmd / .bat 不能被 CreateProcess 直接执行，需要经 cmd /c 调起
            cmd = ["cmd", "/c", npm, *args]
        else:
            cmd = [npm, *args]

        # 忙碌状态（npm 安装无精确进度，进度条滚动）
        self.progress.setRange(0, 0)
        self.progress.setFormat("npm 安装中…")
        self.btn_install.setEnabled(False)
        self.btn_configure.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)

        self.cmd_worker = CommandWorker(cmd)
        self.cmd_worker.log.connect(self._log)
        self.cmd_worker.finished_ok.connect(lambda _: self._on_npm_ok(final))
        self.cmd_worker.finished_fail.connect(self._on_command_fail)
        self.cmd_worker.start()

    # ------------------------------------------------------------------
    def _on_npm_ok(self, final: Path) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("%p%")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setVisible(False)
        self._log("ok", f"npm 安装完成：{final}")
        self._extracted_path = final
        self._configure_env(final)
        self.btn_install.setEnabled(True)
        self.btn_configure.setEnabled(True)
        self._detect_status()

    # ------------------------------------------------------------------
    def _on_command_fail(self, msg: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.btn_install.setEnabled(True)
        self.btn_configure.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setVisible(False)
        if msg and msg != "用户取消":
            self._log("error", f"命令执行失败：{msg}")

    # ------------------------------------------------------------------
    def on_cancel_clicked(self) -> None:
        if self.cmd_worker and self.cmd_worker.isRunning():
            self.cmd_worker.cancel()
        if self.worker and self.worker.isRunning():
            self.worker.cancel()

    # ------------------------------------------------------------------
    def on_configure_clicked(self) -> None:
        """仅配置环境变量：从本地已存在的安装目录中选择最新一个。"""
        install_root = CONFIG_DIR / self.component.key
        if not install_root.exists():
            self._log("warn", "尚未下载，请先执行“下载并安装”。")
            return
        candidates = [p for p in install_root.iterdir() if p.is_dir() and not p.name.startswith(".")
                      and p.name != "downloads"]
        if not candidates:
            self._log("warn", "未找到已解压的安装目录。")
            return
        candidates.sort()
        self._configure_env(candidates[-1])
        self._detect_status()

    # ------------------------------------------------------------------
    def _configure_env(self, install_path: Path) -> None:
        """根据组件类型写入 XXX_HOME 与 PATH。"""
        try:
            comp = self.component
            bin_dir = install_path / comp.path_subdir
            # 若能在安装目录中找到可执行文件，PATH 以它实际所在目录为准
            exe = comp.exec_path_in_home(str(install_path))
            if exe is not None:
                bin_dir = exe.parent
            if comp.env_var:
                if CURRENT_OS == "Windows":
                    EnvManager.set_windows_user_env(comp.env_var, str(install_path))
                    EnvManager.append_windows_path(str(bin_dir))
                else:
                    rc = EnvManager.set_unix_env(comp.env_var, str(install_path))
                    EnvManager.append_unix_path(str(bin_dir))
                    self._log("info", f"已写入 {rc}")
                self._log("ok", f"设置 {comp.env_var}={install_path}")
                self._log("ok", f"追加 PATH：{bin_dir}")
            else:
                if CURRENT_OS == "Windows":
                    EnvManager.append_windows_path(str(bin_dir))
                else:
                    rc = EnvManager.append_unix_path(str(bin_dir))
                    self._log("info", f"已写入 {rc}")
                self._log("ok", f"追加 PATH：{bin_dir}")

            if CURRENT_OS != "Windows":
                self._log("warn", "请打开新的终端或执行 `source ~/.zshrc` 让环境变量生效。")
        except Exception as exc:
            self._log("error", f"环境变量配置失败：{exc}")


# ---------------------------------------------------------------------------
# 捐赠弹窗（不出现在文档中；仅代码内实现）
# ---------------------------------------------------------------------------
class DonateDialog(QDialog):
    """支持作者：微信 / 支付宝 / QQ，各渠道展示对应二维码。"""

    # 每个渠道对应的品牌色、二维码文件名
    CHANNELS = [
        ("微信", "#07C160", "wechat.png"),
        ("支付宝", "#1677FF", "alipay.png"),
        ("QQ", "#EB1923", "qq.png"),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("支持作者")
        self.setFixedSize(380, 402)
        self.setObjectName("donateDialog")
        self._assets_dir = Path(__file__).parent / "assets"
        self._build_ui()
        # 默认展示第一个渠道
        self._show_qr(*self.CHANNELS[0])

    def _build_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        tip = QLabel("如果本工具对你有所帮助，欢迎请作者一杯咖啡 ☕")
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet("font-size:13px;color:#444;")
        v.addWidget(tip)

        # 渠道切换按钮行
        row = QHBoxLayout()
        row.setSpacing(10)
        self._buttons: List[QPushButton] = []
        for name, color, filename in self.CHANNELS:
            btn = QPushButton(name)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setCheckable(True)
            btn.setStyleSheet(
                f"QPushButton{{background:{color};color:white;border:none;border-radius:8px;padding:8px 16px;font-weight:600;}}"
                f"QPushButton:checked{{background:{color};border:2px solid #333;}}"
                f"QPushButton:hover{{background:{color};}}"
            )
            btn.clicked.connect(lambda _=False, n=name, c=color, f=filename: self._show_qr(n, c, f))
            row.addWidget(btn)
            self._buttons.append(btn)
        v.addLayout(row)

        # 当前渠道标签
        self._channel_label = QLabel("")
        self._channel_label.setAlignment(Qt.AlignCenter)
        self._channel_label.setStyleSheet("font-size:14px;font-weight:600;color:#333;")
        v.addWidget(self._channel_label)

        # 二维码展示区（固定尺寸，整体弹窗更紧凑）
        self.qr_view = QLabel("请选择下方渠道")
        self.qr_view.setAlignment(Qt.AlignCenter)
        self.qr_view.setFixedHeight(214)
        self.qr_view.setStyleSheet(
            "background:#fafafa;border:1px solid #e0e0e0;border-radius:10px;color:#888;padding:8px;"
        )
        v.addWidget(self.qr_view, alignment=Qt.AlignHCenter)

        # 底部备注
        note = QLabel("扫码打赏，感谢您的支持！")
        note.setAlignment(Qt.AlignCenter)
        note.setStyleSheet("font-size:12px;color:#999;")
        v.addWidget(note)

    def _show_qr(self, channel: str, color: str = "", filename: str = "") -> None:
        # 更新按钮 checked 状态
        for btn in self._buttons:
            btn.setChecked(btn.text() == channel)

        self._channel_label.setText(f"【{channel}】收款码")
        if color:
            self._channel_label.setStyleSheet(
                f"font-size:15px;font-weight:600;color:{color};"
            )

        if not filename:
            # 兼容旧调用：仅传 channel 时按 CHANNELS 查
            for n, c, f in self.CHANNELS:
                if n == channel:
                    filename = f
                    break

        # 尝试加载二维码图片
        qr_path = self._assets_dir / filename
        if qr_path.exists():
            pixmap = QPixmap(str(qr_path))
            if not pixmap.isNull():
                # 等比缩小到固定边长，整体弹窗更短更美观
                scaled = pixmap.scaled(
                    196, 196,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.qr_view.setPixmap(scaled)
                return

        # 加载失败：显示占位文字
        self.qr_view.clear()
        self.qr_view.setText(
            f"未找到二维码文件：\n\n{qr_path}\n\n请将 {filename} 放入 assets 目录后重启。"
        )


# ---------------------------------------------------------------------------
# 关于我们弹窗
# ---------------------------------------------------------------------------
class AboutDialog(QDialog):
    """关于我们：团队介绍 + QQ/微信群/微信联系方式。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于我们")
        self.setMinimumWidth(760)
        self.setObjectName("aboutDialog")
        self._build_ui()
        self.adjustSize()

    def _build_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(36, 28, 36, 24)
        v.setSpacing(10)

        # ABOUT US 胶囊
        pill = QLabel("ABOUT US")
        pill.setAlignment(Qt.AlignCenter)
        pill.setFixedSize(120, 34)
        pill.setStyleSheet(
            "background:#f0effd;color:#6c5ce7;border:1px solid #dcd7f9;"
            "border-radius:17px;font-weight:700;font-size:13px;"
        )
        v.addWidget(pill, alignment=Qt.AlignHCenter)

        title = QLabel("关于我们")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:30px;font-weight:800;color:#1a1a2e;")
        v.addWidget(title)

        subtitle = QLabel("一群因为热爱而聚在一起的开源爱好者")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size:15px;color:#8a8a9a;")
        v.addWidget(subtitle)
        v.addSpacing(8)

        # 介绍卡片
        card = QFrame()
        card.setObjectName("aboutCard")
        card.setStyleSheet(
            "#aboutCard{background:#ffffff;border:1px solid #e8e8f0;border-radius:16px;}"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(32, 26, 32, 22)
        cl.setSpacing(14)

        heading = QLabel("我们致力于开源项目")
        heading.setStyleSheet("font-size:19px;font-weight:700;color:#222;")
        cl.addWidget(heading)

        p1 = QLabel(
            "我们是一群开源爱好者，专注于分享实用、开箱即用的小工具，"
            "希望能帮你在日常工作中少写一点重复代码、少踩一点坑。"
        )
        p1.setWordWrap(True)
        p1.setStyleSheet("font-size:14px;color:#6b6b7b;line-height:1.6;")
        cl.addWidget(p1)

        # 产品矩阵导流：点击在浏览器打开 nav.qqmu.com
        p_nav = QLabel(
            '更多开箱即用的小工具（MuOpt、MuAsk、JArgus、Jync 等），'
            '欢迎逛逛我们的产品导航：'
            '<a href="https://nav.qqmu.com" style="color:#5b5bd6;'
            'text-decoration:none;font-weight:600;">nav.qqmu.com ↗</a>'
        )
        p_nav.setWordWrap(True)
        p_nav.setCursor(QCursor(Qt.PointingHandCursor))
        p_nav.setStyleSheet("font-size:14px;color:#6b6b7b;line-height:1.6;")
        p_nav.linkActivated.connect(
            lambda url: QDesktopServices.openUrl(QUrl(url))
        )
        cl.addWidget(p_nav)

        p2 = QLabel(
            "如果你有更好的建议或想法，想提需求，或者在使用中遇到软件上的问题，"
            "欢迎随时通过下面的方式联系我们 —— 每一条反馈我们都会认真看："
        )
        p2.setWordWrap(True)
        p2.setStyleSheet("font-size:14px;color:#6b6b7b;line-height:1.6;")
        cl.addWidget(p2)

        # 联系方式 2x2（两行水平布局）
        def contact_row(left_item, right_item) -> QHBoxLayout:
            r = QHBoxLayout()
            r.setSpacing(16)
            r.addWidget(left_item)
            r.addWidget(right_item)
            return r

        cl.addLayout(contact_row(
            self._make_contact_item(
                badge=("QQ", "#e9e8fc", "#5b5bd6"),
                caption="QQ ①",
                value="817094",
                btn_text="点击对话 ↗",
                on_click=lambda: self._open_qq_chat("817094"),
            ),
            self._make_contact_item(
                badge=("QQ", "#e9e8fc", "#5b5bd6"),
                caption="QQ ②",
                value="2912167928",
                btn_text="点击对话 ↗",
                on_click=lambda: self._open_qq_chat("2912167928"),
            ),
        ))
        cl.addSpacing(14)
        cl.addLayout(contact_row(
            self._make_contact_item(
                badge=("群", "#fbeedd", "#d98c2b"),
                caption="QQ 群（点击加群）",
                value="426669837",
                btn_text="点击加群 ↗",
                on_click=lambda: self._copy_contact(
                    "426669837", "QQ 群号已复制，请在 QQ 中搜索群号加入"
                ),
            ),
            self._make_contact_item(
                badge=("微", "#dcf4f4", "#16a3a3"),
                caption="微信（点击复制）",
                value="qqmu66",
                btn_text="复制微信号",
                on_click=lambda: self._copy_contact(
                    "qqmu66", "微信号 qqmu66 已复制，请到微信中添加好友"
                ),
            ),
        ))

        # 操作反馈
        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setStyleSheet("font-size:12px;color:#6c5ce7;")
        cl.addWidget(self.hint_label)

        v.addWidget(card)

    def _make_contact_item(
        self,
        badge: tuple,
        caption: str,
        value: str,
        btn_text: str,
        on_click,
    ) -> QFrame:
        """构造一个联系方式条目（图标 + 名称 + 操作按钮）。"""
        item = QFrame()
        item.setObjectName("contactItem")
        item.setFixedHeight(86)
        item.setStyleSheet(
            "#contactItem{background:#fafafd;border:1px solid #ececf4;border-radius:12px;}"
        )
        h = QHBoxLayout(item)
        h.setContentsMargins(16, 12, 16, 12)
        h.setSpacing(12)

        badge_text, badge_bg, badge_fg = badge
        badge_lbl = QLabel(badge_text)
        badge_lbl.setFixedSize(46, 46)
        badge_lbl.setAlignment(Qt.AlignCenter)
        badge_lbl.setStyleSheet(
            f"background:{badge_bg};color:{badge_fg};border-radius:10px;"
            "font-weight:800;font-size:15px;border:none;"
        )
        h.addWidget(badge_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        caption_lbl = QLabel(caption)
        caption_lbl.setStyleSheet("font-size:12px;color:#9a9aaa;border:none;background:none;")
        value_lbl = QLabel(value)
        value_lbl.setStyleSheet("font-size:18px;font-weight:700;color:#222;border:none;background:none;")
        text_col.addWidget(caption_lbl)
        text_col.addWidget(value_lbl)
        h.addLayout(text_col)
        h.addStretch(1)

        btn = QPushButton(btn_text)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setStyleSheet(
            "QPushButton{background:#ffffff;color:#333;border:1px solid #dcdce6;"
            "border-radius:8px;padding:8px 14px;font-size:13px;}"
            "QPushButton:hover{background:#f4f3ff;border-color:#c8c4f2;color:#5b5bd6;}"
        )
        btn.clicked.connect(on_click)
        h.addWidget(btn)
        return item

    # ------------------------------------------------------------------
    def _copy_to_clipboard(self, text: str) -> None:
        QApplication.clipboard().setText(text)

    def _copy_contact(self, text: str, hint: str) -> None:
        self._copy_to_clipboard(text)
        self.hint_label.setText(f"✓ {hint}：{text}")

    def _open_qq_chat(self, uin: str) -> None:
        """唤起 QQ 临时会话；同时复制 QQ 号，QQ 未安装时可手动添加。"""
        self._copy_to_clipboard(uin)
        QDesktopServices.openUrl(QUrl(f"tencent://message/?uin={uin}&Site=&Menu=yes"))
        self.hint_label.setText(f"✓ 正在唤起 QQ 对话（QQ 号 {uin} 已复制，可手动添加）")


# ---------------------------------------------------------------------------
# 主窗口（无边框自定义标题栏）
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1000, 680)
        self.setMinimumSize(880, 560)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self.components = build_components()
        self._drag_pos: Optional[QPoint] = None
        self._fetch_workers: List[VersionFetchWorker] = []
        self._fetch_pending: int = 0
        # 当前选中的分类 key；搜索关键字直接从搜索框读取
        self._current_category: str = "all"

        self._build_ui()
        self._apply_qss()
        self._load_settings()
        self._start_fetch_versions()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralRoot")
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ------- 自定义标题栏 -------
        self.title_bar = QFrame()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(48)
        tb = QHBoxLayout(self.title_bar)
        tb.setContentsMargins(14, 0, 8, 0)
        tb.setSpacing(6)

        title_label = QLabel(APP_NAME)
        title_label.setObjectName("titleText")
        title_label.setFont(QFont("", 12, QFont.Bold))
        tb.addWidget(title_label)
        tb.addStretch(1)

        # 关于我们
        self.btn_about = QPushButton("💡 关于我们")
        self.btn_about.setObjectName("iconBtn")
        self.btn_about.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_about.setToolTip("了解我们 & 联系方式")
        self.btn_about.clicked.connect(self._on_about_clicked)
        tb.addWidget(self.btn_about)

        # 刷新版本列表按钮
        self.btn_refresh = QPushButton("⟳ 刷新版本")
        self.btn_refresh.setObjectName("iconBtn")
        self.btn_refresh.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_refresh.setToolTip("重新从官网抓取所有组件的可用版本列表")
        self.btn_refresh.clicked.connect(self._start_fetch_versions)
        tb.addWidget(self.btn_refresh)

        # 捐赠图标（不在 README 中提及）
        self.btn_donate = QPushButton("♥")
        self.btn_donate.setObjectName("donateBtn")
        self.btn_donate.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_donate.setToolTip("支持作者")
        self.btn_donate.clicked.connect(self._on_donate_clicked)
        tb.addWidget(self.btn_donate)

        # 窗口控制按钮
        self.btn_min = QPushButton("—")
        self.btn_min.setObjectName("ctrlBtn")
        self.btn_min.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_min.clicked.connect(self.showMinimized)
        tb.addWidget(self.btn_min)

        self.btn_max = QPushButton("▢")
        self.btn_max.setObjectName("ctrlBtn")
        self.btn_max.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_max.clicked.connect(self._toggle_max)
        tb.addWidget(self.btn_max)

        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("closeBtn")
        self.btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_close.clicked.connect(self.close)
        tb.addWidget(self.btn_close)

        outer.addWidget(self.title_bar)

        # ------- 分类筛选 + 搜索栏 -------
        self.filter_bar = QFrame()
        self.filter_bar.setObjectName("filterBar")
        self.filter_bar.setFixedHeight(52)
        fb = QHBoxLayout(self.filter_bar)
        fb.setContentsMargins(18, 8, 18, 8)
        fb.setSpacing(8)

        self.category_buttons: Dict[str, QPushButton] = {}
        for cat in ["all", *CATEGORY_ORDER]:
            chip = QPushButton(CATEGORIES[cat])
            chip.setObjectName("categoryChip")
            chip.setCheckable(True)
            chip.setChecked(cat == "all")
            chip.setCursor(QCursor(Qt.PointingHandCursor))
            chip.clicked.connect(lambda _=False, c=cat: self._on_category_chosen(c))
            fb.addWidget(chip)
            self.category_buttons[cat] = chip
        fb.addSpacing(10)

        self.search_box = QLineEdit()
        self.search_box.setObjectName("searchBox")
        self.search_box.setPlaceholderText("🔍 搜索软件名 / 别名 / 分类名，例如 redis、数据库、kafka、缓存…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedHeight(34)
        self.search_box.textChanged.connect(self._apply_filter)
        fb.addWidget(self.search_box, stretch=1)

        outer.addWidget(self.filter_bar)

        # ------- 主体：卡片列表 + 日志区 -------
        body = QSplitter(Qt.Vertical)
        body.setObjectName("bodySplitter")

        # 卡片滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("cardsScroll")
        cards_wrap = QWidget()
        cards_wrap.setObjectName("cardsWrap")
        cards_layout = QVBoxLayout(cards_wrap)
        cards_layout.setContentsMargins(18, 18, 18, 18)
        cards_layout.setSpacing(14)

        # 按分类分组：每组一个分区标题，其后是该分类的卡片
        by_cat: Dict[str, List[Component]] = {c: [] for c in CATEGORY_ORDER}
        for comp in self.components:
            by_cat[comp.category].append(comp)

        self.cards: List[ComponentCard] = []
        self._cards_by_cat: Dict[str, List[ComponentCard]] = {c: [] for c in CATEGORY_ORDER}
        self.section_headers: Dict[str, QLabel] = {}
        for cat in CATEGORY_ORDER:
            comps = by_cat[cat]
            if not comps:
                continue
            header = QLabel(f"{CATEGORIES[cat]}（{len(comps)}）")
            header.setObjectName("sectionHeader")
            cards_layout.addWidget(header)
            self.section_headers[cat] = header
            for comp in comps:
                card = ComponentCard(comp, self._append_log)
                cards_layout.addWidget(card)
                self.cards.append(card)
                self._cards_by_cat[cat].append(card)
        cards_layout.addStretch(1)
        scroll.setWidget(cards_wrap)
        body.addWidget(scroll)

        # 日志
        log_wrap = QWidget()
        log_wrap.setObjectName("logWrap")
        log_layout = QVBoxLayout(log_wrap)
        log_layout.setContentsMargins(18, 6, 18, 18)
        log_layout.setSpacing(6)
        log_title = QLabel("运行日志")
        log_title.setStyleSheet("font-weight:600;color:#333;")
        log_layout.addWidget(log_title)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("logView")
        log_layout.addWidget(self.log_view)
        body.addWidget(log_wrap)

        body.setStretchFactor(0, 3)
        body.setStretchFactor(1, 2)
        outer.addWidget(body, stretch=1)

        # 底部状态条：左侧系统信息，右侧版本号
        self.status_bar = QFrame()
        self.status_bar.setObjectName("statusBar")
        self.status_bar.setFixedHeight(26)
        sb = QHBoxLayout(self.status_bar)
        sb.setContentsMargins(14, 0, 14, 0)
        sb.setSpacing(0)
        status_left = QLabel(f"系统：{CURRENT_OS} ({MACHINE})   工作目录：{CONFIG_DIR}")
        status_left.setStyleSheet("color:#9aa0ad;background:none;border:none;")
        sb.addWidget(status_left)
        sb.addStretch(1)
        status_version = QLabel(f"版本号 {APP_VERSION}")
        status_version.setStyleSheet("color:#9aa0ad;background:none;border:none;")
        sb.addWidget(status_version)
        outer.addWidget(self.status_bar)

    # ------------------------------------------------------------------
    def _apply_qss(self) -> None:
        """应用 QSS 样式表。"""
        self.setStyleSheet(
            """
            #centralRoot {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #eef2f7, stop:1 #dee5ee);
            }
            #titleBar {
                background: #2c3e50;
                color: white;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            #titleText { color: white; padding-left: 4px; }
            #iconBtn, #donateBtn, #ctrlBtn, #closeBtn {
                background: transparent;
                color: white;
                border: none;
                padding: 6px 12px;
                font-size: 14px;
                border-radius: 6px;
            }
            #iconBtn:hover, #ctrlBtn:hover, #donateBtn:hover {
                background: rgba(255,255,255,0.15);
            }
            #donateBtn { color: #ff8181; font-size: 18px; }
            #closeBtn:hover { background: #e74c3c; }

            /* ----------------- 分类筛选 / 搜索栏 ----------------- */
            #filterBar {
                background: rgba(255,255,255,0.75);
                border-bottom: 1px solid #dde3ea;
            }
            QPushButton#categoryChip {
                background: #ffffff;
                color: #546e7a;
                border: 1px solid #cfd8dc;
                border-radius: 15px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton#categoryChip:hover {
                border-color: #90caf9;
                color: #1976d2;
            }
            QPushButton#categoryChip:checked {
                background: #1976d2;
                color: white;
                border-color: #1976d2;
                font-weight: 600;
            }
            #searchBox {
                background: white;
                border: 1px solid #cfd8dc;
                border-radius: 8px;
                padding: 0 12px;
                font-size: 13px;
                color: #263238;
            }
            #searchBox:hover { border-color: #90caf9; }
            #searchBox:focus { border-color: #1976d2; }
            #sectionHeader {
                color: #37474f;
                font-size: 14px;
                font-weight: 700;
                padding: 4px 2px;
            }

            #cardsScroll { border: none; background: transparent; }
            #cardsWrap { background: transparent; }
            #card {
                background: white;
                border-radius: 12px;
                border: 1px solid #e6ebf1;
            }
            #cardTitle { color: #263238; }
            #statusLabel { font-size: 12px; }
            #fieldLabel { color:#546e7a; font-size:13px; }

            /* ----------------- 下拉框 ----------------- */
            QComboBox {
                padding: 0 34px 0 12px;
                border: 1px solid #cfd8dc;
                border-radius: 8px;
                background: white;
                color: #263238;
                font-size: 13px;
                min-height: 32px;
                selection-background-color: #1976d2;
            }
            QComboBox:hover  { border-color: #90caf9; }
            QComboBox:focus  { border-color: #1976d2; }
            QComboBox:on     { border-color: #1976d2; }
            QComboBox QLineEdit {
                border: none;
                background: transparent;
                padding: 0;
                margin: 0;
                color: #263238;
                font-size: 13px;
                selection-background-color: #1976d2;
                selection-color: white;
            }
            QComboBox QLineEdit:focus { outline: none; }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 30px;
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0;
                height: 0;
            }
            #comboArrow {
                color: #78909c;
                font-size: 14px;
                background: transparent;
                border: none;
                padding-right: 6px;
            }
            QComboBox:hover #comboArrow { color: #1976d2; }
            QComboBox:focus #comboArrow { color: #1976d2; }
            QComboBox QAbstractItemView {
                border: 1px solid #cfd8dc;
                border-radius: 8px;
                background: white;
                padding: 6px;
                outline: 0;
                selection-background-color: #1976d2;
                selection-color: white;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px 14px;
                border-radius: 6px;
                min-height: 24px;
                color: #263238;
            }
            QComboBox QAbstractItemView::item:hover {
                background: #e3f2fd;
                color: #0d47a1;
            }
            QComboBox QAbstractItemView::item:selected {
                background: #1976d2;
                color: white;
            }

            QPushButton#primaryBtn {
                background: #1976d2;
                color: white;
                border: none;
                padding: 6px 18px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton#primaryBtn:hover { background: #1e88e5; }
            QPushButton#primaryBtn:pressed { background: #1565c0; }
            QPushButton#primaryBtn:disabled { background: #b0bec5; color:#eceff1; }

            QPushButton#secondaryBtn {
                background: #ffffff;
                color: #1976d2;
                border: 1px solid #1976d2;
                padding: 6px 16px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton#secondaryBtn:hover { background: #e3f2fd; }
            QPushButton#secondaryBtn:pressed { background: #bbdefb; }
            QPushButton#secondaryBtn:disabled {
                color: #b0bec5;
                border-color: #cfd8dc;
                background: #f5f7fa;
            }

            QPushButton#dangerBtn {
                background: #ffffff;
                color: #c62828;
                border: 1px solid #c62828;
                padding: 6px 16px;
                border-radius: 8px;
                font-size: 13px;
            }
            QPushButton#dangerBtn:hover { background: #ffebee; }
            QPushButton#dangerBtn:disabled { color:#e0a4a4; border-color:#e0a4a4; }

            QProgressBar {
                background: #eceff1;
                border: none;
                border-radius: 6px;
                height: 14px;
                text-align: center;
                color: #263238;
                font-size: 11px;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #26c6da, stop:1 #1976d2);
            }

            #logWrap { background: transparent; }
            #logView {
                background: #1e1e2e;
                color: #dcdcdc;
                border-radius: 8px;
                padding: 6px;
                font-family: Menlo, Consolas, "Courier New", monospace;
                font-size: 12px;
            }
            #statusBar {
                background: #eceff1;
                color: #455a64;
                font-size: 12px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 4px 0;
            }
            QScrollBar::handle:vertical {
                background: #b0bec5;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #90a4ae; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

            QToolTip {
                background: #37474f;
                color: white;
                border: 1px solid #263238;
                padding: 6px 10px;
                border-radius: 6px;
            }
            """
        )

    # ------------------------------------------------------------------
    # 无边框窗口拖动
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.title_bar.underMouse():
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if self.title_bar.underMouse():
            self._toggle_max()

    def _toggle_max(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.btn_max.setText("▢")
        else:
            self.showMaximized()
            self.btn_max.setText("❐")

    # ------------------------------------------------------------------
    # 分类筛选 & 搜索
    # ------------------------------------------------------------------
    def _on_category_chosen(self, cat: str) -> None:
        """点击分类胶囊：更新选中态并重新过滤卡片。"""
        self._current_category = cat
        for c, chip in self.category_buttons.items():
            chip.setChecked(c == cat)
        self._apply_filter()

    def _match_keyword(self, comp: Component, keyword: str) -> bool:
        """关键字在 显示名 / key / 分类名 / 别名 中做大小写不敏感的包含匹配。"""
        haystack = [comp.display_name, comp.key, CATEGORIES.get(comp.category, ""), *comp.aliases]
        return any(keyword in str(x).lower() for x in haystack)

    def _apply_filter(self) -> None:
        """分类与关键字取交集；某个分类下没有可见卡片时连分区标题一起隐藏。"""
        keyword = self.search_box.text().strip().lower()
        for cat, header in self.section_headers.items():
            any_visible = False
            for card in self._cards_by_cat[cat]:
                ok_category = self._current_category in ("all", cat)
                ok_keyword = (not keyword) or self._match_keyword(card.component, keyword)
                visible = ok_category and ok_keyword
                card.setVisible(visible)
                if visible:
                    any_visible = True
            header.setVisible(any_visible)

    # ------------------------------------------------------------------
    def _start_fetch_versions(self) -> None:
        """从各官网并发拉取版本列表。可反复调用（刷新）。"""
        # 若有 worker 仍在运行，等它跑完再触发新一轮
        alive = [w for w in self._fetch_workers if w.isRunning()]
        if alive:
            self._append_log("warn", f"仍有 {len(alive)} 个抓取任务在进行，请稍候…")
            return
        # 清理已完成的 worker
        for w in self._fetch_workers:
            w.deleteLater()
        self._fetch_workers.clear()

        if hasattr(self, "btn_refresh"):
            self.btn_refresh.setEnabled(False)
            self.btn_refresh.setText("⟳ 抓取中…")
        self._fetch_pending = 0
        self._append_log("info", "正在从各官网获取最新版本列表…")
        for card in self.cards:
            fetcher = FETCHERS.get(card.component.key)
            if not fetcher:
                continue
            w = VersionFetchWorker(card.component.key, fetcher, self)
            w.done.connect(self._on_versions_fetched)
            self._fetch_workers.append(w)
            self._fetch_pending += 1
            w.start()

    def _on_versions_fetched(self, key: str, versions) -> None:
        card = next((c for c in self.cards if c.component.key == key), None)
        if card:
            if versions is None:
                self._append_log("warn", f"[{card.component.display_name}] 官网版本获取失败，使用内置默认列表")
            else:
                card.set_versions(versions)
        self._fetch_pending -= 1
        if self._fetch_pending <= 0 and hasattr(self, "btn_refresh"):
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText("⟳ 刷新版本")
            self._append_log("info", "版本列表获取完成。")

    # ------------------------------------------------------------------
    def _on_donate_clicked(self) -> None:
        DonateDialog(self).exec()

    # ------------------------------------------------------------------
    def _on_about_clicked(self) -> None:
        AboutDialog(self).exec()

    # ------------------------------------------------------------------
    def _append_log(self, level: str, msg: str) -> None:
        color = {
            "info": "#dcdcdc",
            "ok": "#7CFC7C",
            "warn": "#FFB347",
            "error": "#FF6B6B",
        }.get(level, "#dcdcdc")
        self.log_view.append(f'<span style="color:{color};">{msg}</span>')

    # ------------------------------------------------------------------
    def _load_settings(self) -> None:
        """加载上次选择的版本。"""
        if not CONFIG_FILE.exists():
            return
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            selections = data.get("selections", {})
            for card in self.cards:
                v = selections.get(card.component.key)
                if v:
                    idx = card.version_combo.findText(v)
                    if idx >= 0:
                        card.version_combo.setCurrentIndex(idx)
        except Exception:
            pass

    def _save_settings(self) -> None:
        try:
            ensure_dir(CONFIG_DIR)
            data = {
                "selections": {
                    card.component.key: card.version_combo.currentText()
                    for card in self.cards
                }
            }
            CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        self._save_settings()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    ensure_dir(CONFIG_DIR)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
