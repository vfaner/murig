# -*- coding: utf-8 -*-
"""组件数据模型与系统探测逻辑。"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .constants import CURRENT_OS
from .env import EnvManager
from .workspace import WS


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
    # GUI 应用（如 CC-Switch）：探测时**绝不执行**它的可执行文件，否则会弹出
    # 程序窗口（表现为安装后反复打开/关闭）。未显式声明时也会按 PE 头自动识别
    gui_app: bool = False

    def install_dir(self, version: str) -> Path:
        """返回该版本组件的解压安装目录（跟随工作空间配置）。"""
        return WS.resolve(self.key, self.category) / self.key / f"{self.key}-{version}"

    def workspace_root(self) -> Path:
        """该组件当前的工作空间根目录。"""
        return WS.resolve(self.key, self.category)

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

        # 1) 优先通过 XXX_HOME 环境变量判断。
        #    用户变量优先于系统变量：Windows 合并环境变量时「系统在前」，
        #    系统变量里可能还留着旧版本（进程环境是启动时的合并快照），
        #    而本工具新装的版本写入的是用户变量——直接 get 会命中旧值
        if self.env_var:
            home = EnvManager.user_registry_env(self.env_var) or EnvManager.get(self.env_var)
            if home:
                exe = self.exec_path_in_home(home)
                if exe is not None:
                    return DetectResult(
                        installed=True,
                        source=self.env_var,
                        home=home,
                        exe_path=str(exe),
                        version_text=_probe_version(str(exe), self.version_args, self.gui_app),
                    )

        # 2) 通过 PATH 中的可执行文件。Windows 上先查用户 PATH（注册表
        #    HKCU\Environment），再回退完整 PATH：否则系统 PATH 里的旧版本
        #    会一直被 which 命中，掩盖用户新装的版本
        exe_name_final = self.exec_name + (".exe" if CURRENT_OS == "Windows" else "")
        if CURRENT_OS == "Windows":
            for d in EnvManager.user_path_dirs():
                base = Path(d)
                candidates = [base / exe_name_final]
                if self.path_subdir:
                    candidates.insert(0, base / self.path_subdir / exe_name_final)
                for cand in candidates:
                    if cand.is_file():
                        return DetectResult(
                            installed=True,
                            source="PATH（用户）",
                            exe_path=str(cand),
                            version_text=_probe_version(
                                str(cand), self.version_args, self.gui_app),
                        )
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
                        version_text=_probe_version(str(exe), self.version_args, self.gui_app),
                    )

        # 4) 扫描工作空间：环境变量被清掉后仍能认回本工具装过的组件
        for root in WS.roots_for(self.key, self.category):
            base = root / self.key
            if not base.exists():
                continue
            homes = [
                p for p in base.iterdir()
                if p.is_dir() and not p.name.startswith(".") and p.name != "downloads"
            ]
            for home in sorted(homes, reverse=True):
                exe = self.exec_path_in_home(str(home))
                if exe is not None:
                    return DetectResult(
                        installed=True,
                        source="工作空间",
                        home=str(home),
                        exe_path=str(exe),
                        version_text=_probe_version(str(exe), self.version_args, self.gui_app),
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


def _is_gui_program(exe: str) -> bool:
    """判断可执行文件是否是 GUI 程序（执行它会弹窗口，不能用来探测版本）。

    Windows：读 PE 头的 Subsystem 字段（2=WINDOWS_GUI）。
    其它平台：按 AppImage / .app 这类明显特征启发式判断。
    """
    try:
        if CURRENT_OS == "Windows":
            if not exe.lower().endswith(".exe"):
                return False  # .cmd/.bat 由 shell 承载，按 CLI 处理
            with open(exe, "rb") as f:
                if f.read(2) != b"MZ":
                    return False
                f.seek(0x3C)
                pe_off = int.from_bytes(f.read(4), "little")
                f.seek(pe_off)
                if f.read(4) != b"PE\0\0":
                    return False
                # Optional header 起于 pe_off+24；Subsystem 位于 optional+68
                # （PE32 与 PE32+ 偏移恰好相同）
                f.seek(pe_off + 24 + 68)
                subsystem = int.from_bytes(f.read(2), "little")
                return subsystem in (2, 9)  # IMAGE_SUBSYSTEM_WINDOWS_GUI / WINDOWS_CE_GUI
        if exe.endswith(".AppImage"):
            return True
        if ".app/Contents/MacOS" in exe or exe.endswith(".app"):
            return True
    except Exception:
        return False
    return False


# 版本探测缓存：(exe + args) -> (时间戳, 版本串)。
# 卡片构造 / 安装完成后 / 工作空间变更都会触发检测，缓存避免同一程序被反复执行
_VERSION_CACHE: Dict[str, Tuple[float, str]] = {}
_VERSION_TTL = 300.0


def _probe_version(exe: str, args: List[str], gui_app: bool = False) -> str:
    """调用可执行文件抓取版本号；失败返回空串。

    GUI 程序直接跳过：执行它会真的打开程序窗口，检测一次就弹一次，
    直到超时被杀掉——这正是「安装后应用反复打开又关闭」的原因。
    """
    if not args:
        return ""
    if gui_app or _is_gui_program(exe):
        return ""

    key = f"{exe}|{' '.join(args)}"
    now = time.time()
    hit = _VERSION_CACHE.get(key)
    if hit and now - hit[0] < _VERSION_TTL:
        return hit[1]

    try:
        kwargs: Dict = {}
        if CURRENT_OS == "Windows":
            # 不给 CLI 程序创建控制台窗口（.cmd/.bat 尤其明显）
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            # 不用系统 locale（Windows 上是 GBK）：命令输出含非本地编码字节会
            # 在读取线程里抛 UnicodeDecodeError
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
            **kwargs,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        line = next((ln.strip() for ln in out.splitlines() if ln.strip()), "")
        line = line[:80]
        _VERSION_CACHE[key] = (now, line)
        return line
    except Exception:
        return ""
