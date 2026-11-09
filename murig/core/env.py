# -*- coding: utf-8 -*-
"""跨平台环境变量读写。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from .constants import CURRENT_OS


# ---------------------------------------------------------------------------
# 环境变量处理
# ---------------------------------------------------------------------------
class EnvManager:
    """跨平台环境变量管理器。"""

    @staticmethod
    def get(name: str) -> Optional[str]:
        return os.environ.get(name)

    # ------------------------------------------------------------------
    # Windows 注册表级读取：区分用户变量与系统变量。
    # 背景：Windows 合并 PATH 时「系统在前、用户在后」，且进程拿到的是启动
    # 时的合并快照——系统里装过的旧版本会一直压过用户新写入的版本。
    # ------------------------------------------------------------------
    @staticmethod
    def user_registry_env(name: str) -> Optional[str]:
        """读 Windows 用户环境变量（HKCU\\Environment），不存在返回 None。"""
        if CURRENT_OS != "Windows":
            return None
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ
            ) as key:
                value, _reg_type = winreg.QueryValueEx(key, name)
            if isinstance(value, str) and "%" in value:
                value = os.path.expandvars(value)
            return (value or None) if isinstance(value, str) else None
        except OSError:
            return None

    @staticmethod
    def user_path_dirs() -> list:
        """用户 PATH 目录列表（已展开、去重、保序）。"""
        raw = EnvManager.user_registry_env("Path") or ""
        out: list = []
        for p in raw.split(";"):
            p = p.strip().strip('"')
            if p and p.upper() not in {d.upper() for d in out}:
                out.append(p)
        return out

    @staticmethod
    def system_path_exec_dirs(exec_name: str) -> list:
        """系统 PATH（HKLM）中包含该可执行文件的目录——用于提示旧版本冲突。"""
        if CURRENT_OS != "Windows":
            return []
        import winreg  # type: ignore

        exe = exec_name + ".exe"
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                0, winreg.KEY_READ,
            ) as key:
                value, _reg_type = winreg.QueryValueEx(key, "Path")
        except OSError:
            return []
        hits: list = []
        for p in value.split(";"):
            p = p.strip().strip('"')
            if p and (Path(os.path.expandvars(p)) / exe).exists():
                hits.append(p)
        return hits

    @staticmethod
    def open_env_editor() -> str:
        """打开 Windows「环境变量」编辑窗口，优先以管理员权限启动。

        普通权限打开的窗口里系统变量是只读的（点了没反应、也不提示提权），
        所以这里用 ShellExecute 的 runas 动词触发 UAC 提权；提权失败（用户
        取消 UAC、非管理员）再退化为普通打开，至少能查看用户变量。

        返回 "admin"（已提权启动）/ "user"（未提权，系统变量只读）/ ""（失败）。
        """
        if CURRENT_OS != "Windows":
            return ""
        import ctypes

        # sysdm.cpl,EditEnvironmentVariables：直接打开环境变量对话框
        # （而不是系统属性的高级页，省得用户再点一次）
        args = "sysdm.cpl,EditEnvironmentVariables"
        try:
            shell = ctypes.windll.shell32
            if shell.ShellExecuteW(None, "runas", "rundll32.exe", args, None, 1) > 32:
                return "admin"
            # rc <= 32：用户取消 UAC、无管理员或 runas 不可用 -> 普通打开兜底
            if shell.ShellExecuteW(None, "open", "rundll32.exe", args, None, 1) > 32:
                return "user"
        except Exception:
            pass
        return ""

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
