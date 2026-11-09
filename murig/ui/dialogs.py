# -*- coding: utf-8 -*-
"""对话框：关于、设置。"""

from __future__ import annotations

from typing import Dict

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QCursor, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..core.constants import (
    APP_VERSION, CATEGORIES, CATEGORY_ORDER, CONFIG_DIR, RELEASES_LATEST_URL,
    REPO_URL,
)
from ..core.mirrors import MIRRORS, PRESETS
from ..core.settings import INSTALL, UI
from ..core.updates import is_newer
from ..core.utils import human_size, open_in_file_manager
from ..core.workers import MirrorProbeWorker, UpdateCheckWorker
from .fonts import MISANS_FAMILY, apply_app_font, misans_available
from ..core.workspace import WS
from ..resources import icon_path
from .widgets import ToggleSwitch


class NoWheelComboBox(QComboBox):
    """未下拉时忽略滚轮：防止在滚动页面时光标扫过下拉框误改选中项。"""

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()


# ---------------------------------------------------------------------------
# 关于我们弹窗
# ---------------------------------------------------------------------------
class AboutDialog(QDialog):
    """关于我们：项目溯源（基于 MuRig v1.2.0 二次开发）。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于我们")
        self.setObjectName("aboutDialog")
        self._build_ui()
        # 宽高按内容自适应，超出屏幕的部分交给滚动条
        hint = self._body.sizeHint()
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            max_w, max_h = int(avail.width() * 0.94), int(avail.height() * 0.9)
        else:
            max_w, max_h = 1000, 860
        self.resize(min(max(560, hint.width()), max_w),
                    min(hint.height() + 12, max(360, max_h)))

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._body = QWidget()
        outer.addWidget(scroll)

        v = QVBoxLayout(self._body)
        v.setContentsMargins(32, 24, 32, 18)
        v.setSpacing(12)
        scroll.setWidget(self._body)

        # 头部：图标 + 应用名 / 副标题横排，压缩纵向空间
        # （窗口标题已是「关于我们」，正文不再重复一行大标题）
        header = QHBoxLayout()
        header.setSpacing(14)
        logo = QLabel()
        logo.setObjectName("aboutLogo")
        icon_file = icon_path()
        if icon_file.exists():
            pm = QIcon(str(icon_file)).pixmap(56, 56)
            if not pm.isNull():
                logo.setPixmap(pm)
        header.addWidget(logo, alignment=Qt.AlignVCenter)

        head_col = QVBoxLayout()
        head_col.setSpacing(2)
        title = QLabel("MuRig")
        title.setObjectName("aboutTitle")
        head_col.addWidget(title)
        subtitle = QLabel(f"一群因为热爱而聚在一起的开源爱好者 · {APP_VERSION}")
        subtitle.setObjectName("aboutSubtitle")
        head_col.addWidget(subtitle)
        header.addLayout(head_col)
        header.addStretch(1)
        v.addLayout(header)

        # 项目溯源：本工具由开源项目 MuRig 二次开发而来
        origin = QFrame()
        origin.setObjectName("aboutCard")
        ol = QVBoxLayout(origin)
        ol.setContentsMargins(26, 18, 26, 16)
        ol.setSpacing(8)

        origin_heading = QLabel("项目溯源")
        origin_heading.setObjectName("aboutHeading")
        ol.addWidget(origin_heading)

        origin_text = QLabel(
            "本工具基于开源项目 "
            '<a href="https://github.com/vfaner/murig" style="color:#5b5bd6;'
            'text-decoration:none;font-weight:600;">MuRig v1.2.0 ↗</a>'
            " 制作演变而来：沿用其组件装配与环境配置的核心能力，并在此基础上"
            "新增、修复了部分功能，让下载安装与环境配置更顺手省心。<br><br>"
            "原项目由 "
            '<a href="https://nav.qqmu.com" style="color:#5b5bd6;'
            'text-decoration:none;font-weight:600;">沐编程</a>'
            " 以 MIT 协议开源，在此致谢；本版本在保留原作者署名与授权的前提下"
            "进行二次开发与维护。"
        )
        origin_text.setWordWrap(True)
        origin_text.setOpenExternalLinks(True)
        origin_text.setToolTip("https://github.com/vfaner/murig")
        origin_text.setObjectName("aboutText")
        ol.addWidget(origin_text)

        v.addWidget(origin)

        # 当前项目：仓库地址与发行版下载入口
        proj = QFrame()
        proj.setObjectName("aboutCard")
        pl = QVBoxLayout(proj)
        pl.setContentsMargins(26, 18, 26, 16)
        pl.setSpacing(8)

        proj_heading = QLabel("当前项目")
        proj_heading.setObjectName("aboutHeading")
        pl.addWidget(proj_heading)

        proj_text = QLabel(
            "本版本仓库："
            f'<a href="{REPO_URL}" style="color:#5b5bd6;'
            f'text-decoration:none;font-weight:600;">{REPO_URL.removeprefix("https://")} ↗</a>'
            "<br><br>"
            "已打包的可执行文件在 "
            f'<a href="{RELEASES_LATEST_URL}" '
            'style="color:#5b5bd6;text-decoration:none;font-weight:600;">'
            "Releases 最新版 ↗</a>"
            " 获取（Windows / macOS / Linux 均由 GitHub Actions 自动构建）。"
            "<br><br>"
            "「设置 → 软件更新」可手动检查最新版本；提 Issue、看更新记录或参与改进，"
            "欢迎到仓库里来。"
        )
        proj_text.setWordWrap(True)
        proj_text.setOpenExternalLinks(True)
        proj_text.setToolTip(REPO_URL)
        proj_text.setObjectName("aboutText")
        pl.addWidget(proj_text)

        v.addWidget(proj)

        # 底注：协议与溯源一句话
        foot = QLabel("以 MIT 协议开源 · 基于开源项目 MuRig v1.2.0 二次开发")
        foot.setAlignment(Qt.AlignCenter)
        foot.setObjectName("aboutFoot")
        v.addWidget(foot)


# ---------------------------------------------------------------------------
# 设置对话框
# ---------------------------------------------------------------------------
class WorkspaceDialog(QDialog):
    """设置：工作空间目录 + 下载通道 + 安装选项 + 安装包清理。

    修改即时生效并落盘；关闭时若有过修改则以 Accepted 返回，供主窗口刷新卡片。
    """

    def __init__(self, parent=None, log_cb=None, names=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        # 固定合理宽度：路径用省略号截断（tooltip 看全名），不再被长路径撑宽
        self.setObjectName("workspaceDialog")
        self._log_cb = log_cb
        self._names = names or {}
        self.changed = False
        self._build_ui()
        screen = QApplication.primaryScreen()
        max_h = int(screen.availableGeometry().height() * 0.88) if screen else 860
        # 不超过主窗口的纵向长度：设置弹窗比主应用还高会显得失衡
        parent = self.parent()
        if parent is not None and parent.height() > 200:
            max_h = min(max_h, parent.height())
        self.resize(640, min(self._body.sizeHint().height() + 4, max_h))

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 14)
        outer.setSpacing(10)

        tip = QLabel(
            "安装位置解析优先级：组件自定义 ＞ 分类工作空间 ＞ 全局默认 ＞ 内置默认目录。"
            "修改立即生效；已安装的组件保持原地不动，不会自动迁移。"
        )
        tip.setWordWrap(True)
        tip.setObjectName("dialogTip")
        outer.addWidget(tip)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        self._body = body
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # 全局默认
        grp = QGroupBox("全局默认工作空间")
        g = QGridLayout(grp)
        g.setColumnStretch(1, 1)
        g.setHorizontalSpacing(12)
        name = QLabel("所有组件")
        name.setObjectName("pathName")
        name.setMinimumWidth(64)
        g.addWidget(name, 0, 0)
        self._global_label = QLabel()
        self._global_label.setObjectName("pathValue")
        g.addWidget(self._global_label, 0, 1)
        g.addWidget(self._mini_btn(
            "浏览", "选择目录作为全局默认工作空间",
            self._on_browse_global), 0, 2)
        g.addWidget(self._mini_btn(
            "重置", "恢复为内置默认目录",
            lambda *_args: self._reset(
                lambda: WS.set_global(None), "全局默认工作空间")), 0, 3)
        g.addWidget(self._mini_btn(
            "打开", "在系统文件管理器中打开该目录",
            lambda *_args: self._open_dir(WS.global_ws or CONFIG_DIR)), 0, 4)
        v.addWidget(grp)

        # 分类工作空间
        grp = QGroupBox("分类工作空间（留空表示跟随全局）")
        g = QGridLayout(grp)
        g.setColumnStretch(1, 1)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)
        self._cat_labels: Dict[str, QLabel] = {}
        for row, cat in enumerate(CATEGORY_ORDER):
            name = QLabel(CATEGORIES[cat])
            name.setObjectName("pathName")
            name.setMinimumWidth(64)
            g.addWidget(name, row, 0)
            lab = QLabel()
            lab.setObjectName("pathValue")
            self._cat_labels[cat] = lab
            g.addWidget(lab, row, 1)
            g.addWidget(self._mini_btn(
                "浏览", f"选择「{CATEGORIES[cat]}」的工作空间目录",
                # clicked 会传入 checked 参数：用 *_args 吃掉，避免覆盖 c 的默认值
                lambda *_args, c=cat: self._browse(
                    f"选择「{CATEGORIES[c]}」的工作空间",
                    str(WS.categories.get(c) or WS.global_ws or CONFIG_DIR),
                    lambda p, c=c: WS.set_category(c, p),
                    f"分类「{CATEGORIES[c]}」工作空间",
                )), row, 2)
            g.addWidget(self._mini_btn(
                "重置", "清除该分类设置，跟随全局",
                lambda *_args, c=cat: self._reset(
                    lambda c=c: WS.set_category(c, None),
                    f"分类「{CATEGORIES[c]}」工作空间")), row, 3)
            g.addWidget(self._mini_btn(
                "打开", "在系统文件管理器中打开该目录",
                lambda *_args, c=cat: self._open_dir(
                    WS.categories.get(c) or WS.global_ws or CONFIG_DIR)), row, 4)
        v.addWidget(grp)

        # 组件自定义覆盖：没有自定义目录时整组隐藏，不占空间
        grp = QGroupBox("组件自定义目录（在组件卡片点文件夹按钮设置，此处可清除）")
        self._override_grp = grp
        self._override_box = QVBoxLayout(grp)
        self._override_box.setSpacing(6)
        v.addWidget(grp)

        # 下载加速（镜像源）
        grp = QGroupBox("下载加速（GitHub Release 镜像源）")
        g = QGridLayout(grp)
        g.setColumnStretch(1, 1)
        g.addWidget(QLabel("下载通道"), 0, 0)
        self._mirror_combo = NoWheelComboBox()
        self._mirror_combo.addItem("自动（测速选最快，优势不大则直连）", "auto")
        self._mirror_combo.addItem("直连（不使用镜像）", "direct")
        for m in PRESETS:
            self._mirror_combo.addItem(m.name, m.id)
        self._mirror_combo.addItem("自定义…", "custom")
        idx = self._mirror_combo.findData(MIRRORS.mode)
        self._mirror_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._mirror_combo.currentIndexChanged.connect(self._on_mirror_changed)
        g.addWidget(self._mirror_combo, 0, 1)

        self._probe_btn = self._mini_btn("测速", "对各下载通道抽样测速", self._start_probe)
        g.addWidget(self._probe_btn, 0, 2)

        self._custom_edit = QLineEdit(MIRRORS.custom)
        self._custom_edit.setPlaceholderText("自定义镜像模板，如 https://your-mirror.com/{url}")
        self._custom_edit.textChanged.connect(self._on_custom_changed)
        # 仅在选择「自定义…」时显示模板行
        self._tmpl_label = QLabel("模板")
        self._tmpl_label.setVisible(MIRRORS.mode == "custom")
        self._custom_edit.setVisible(MIRRORS.mode == "custom")
        g.addWidget(self._tmpl_label, 1, 0)
        g.addWidget(self._custom_edit, 1, 1, 1, 2)

        g.addWidget(QLabel("并行分块"), 3, 0)
        self._parts_combo = NoWheelComboBox()
        for n in (1, 2, 4, 8):
            self._parts_combo.addItem(
                "关闭（单线程）" if n == 1 else f"{n} 段", n)
        pidx = self._parts_combo.findData(MIRRORS.parts)
        self._parts_combo.setCurrentIndex(pidx if pidx >= 0 else 2)
        self._parts_combo.currentIndexChanged.connect(self._on_parts_changed)
        g.addWidget(self._parts_combo, 3, 1)

        # 未测速时不占位显示，点「测速」或出结果后才出现
        self._probe_label = QLabel()
        self._probe_label.setObjectName("pathValue")
        self._probe_label.setWordWrap(True)
        self._probe_label.setVisible(False)
        g.addWidget(self._probe_label, 2, 1, 1, 2)
        v.addWidget(grp)

        # 安装与更新：行为开关 + 安装包清理 + 版本检查合并为一组，减少卡片占高
        grp = QGroupBox("安装与更新")
        g = QGridLayout(grp)
        g.setColumnStretch(0, 1)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        # 滑动开关：默认复选框样式太淡，看不出是可交互的选项
        self._auto_env_box = ToggleSwitch("安装完成后自动配置环境变量")
        self._auto_env_box.setChecked(INSTALL.auto_env)
        self._auto_env_box.setToolTip(
            "写入 XXX_HOME 与 PATH 会改动系统/用户配置；关闭时只下载解压，"
            "需要时在组件卡片点「配置环境变量」"
        )
        self._auto_env_box.toggled.connect(self._on_auto_env_changed)
        g.addWidget(self._auto_env_box, 0, 0)
        self._auto_clean_box = ToggleSwitch("安装完成后自动清理下载的安装包")
        self._auto_clean_box.setChecked(INSTALL.auto_clean)
        self._auto_clean_box.setToolTip(
            "组件解压安装完成后自动删除 downloads 目录里的压缩包；"
            "关闭后保留安装包，便于重装或离线复用，可随时用「立即清理」手动删除"
        )
        self._auto_clean_box.toggled.connect(self._on_auto_clean_changed)
        g.addWidget(self._auto_clean_box, 1, 0)

        # 安装包清理
        self._cache_label = QLabel()
        self._cache_label.setObjectName("pathValue")
        self._cache_label.setWordWrap(True)
        g.addWidget(self._cache_label, 2, 0)
        self._clean_btn = self._mini_btn(
            "立即清理", "删除所有工作空间 downloads 目录里的安装包，已安装组件不受影响",
            self._clean_downloads)
        g.addWidget(self._clean_btn, 2, 1)
        self._refresh_cache_label()

        # 软件更新：手动点「检查更新」查 GitHub 上的最新 Release
        self._update_label = QLabel()
        self._update_label.setObjectName("pathValue")
        self._update_label.setWordWrap(True)
        self._update_label.setText(f"当前版本 {APP_VERSION}")
        g.addWidget(self._update_label, 3, 0)
        self._update_btn = self._mini_btn(
            "检查更新", "连接 GitHub 查询本项目的最新发布版本（需要联网）",
            self._start_update_check)
        g.addWidget(self._update_btn, 3, 1)
        v.addWidget(grp)

        # 界面字体：默认用内置 MiSans，打开开关则回系统字体
        grp = QGroupBox("界面字体")
        g = QGridLayout(grp)
        g.setColumnStretch(0, 1)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        self._sysfont_box = ToggleSwitch("使用系统字体（关闭时使用内置 MiSans）")
        self._sysfont_box.setChecked(UI.system_font)
        self._sysfont_box.setToolTip(
            "关闭时使用内置的 MiSans 渲染界面，避免不同系统字体导致的版式差异；"
            "打开则跟随系统界面字体（Windows 雅黑 / macOS 苹方 / Linux 桌面字体）"
        )
        self._sysfont_box.toggled.connect(self._on_sysfont_changed)
        g.addWidget(self._sysfont_box, 0, 0)
        self._font_label = QLabel()
        self._font_label.setObjectName("pathValue")
        self._font_label.setWordWrap(True)
        g.addWidget(self._font_label, 1, 0)
        self._refresh_font_label()
        v.addWidget(grp)

        v.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)

        btn = QPushButton("关闭")
        btn.setObjectName("primaryBtn")
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setFixedHeight(36)
        btn.clicked.connect(lambda: self.accept() if self.changed else self.reject())
        outer.addWidget(btn, alignment=Qt.AlignRight)

        self._refresh()

    # ------------------------------------------------------------------
    def _on_browse_global(self, *_args) -> None:
        self._browse(
            "选择全局默认工作空间",
            str(WS.global_ws or CONFIG_DIR),
            lambda p: WS.set_global(p),
            "全局默认工作空间",
        )

    @staticmethod
    def _elide_mid(text: str, limit: int = 30) -> str:
        """路径过长时中间省略，保住盘符与末级目录名。"""
        if len(text) <= limit:
            return text
        head = (limit - 1) // 2
        tail = limit - 1 - head
        return f"{text[:head]}…{text[len(text) - tail:]}"

    def _mini_btn(self, text: str, tip: str, cb) -> QPushButton:
        """紧凑的小按钮（浏览/重置/打开等），比 secondaryBtn 更矮更窄。"""
        btn = QPushButton(text)
        btn.setObjectName("miniBtn")
        btn.setFixedHeight(28)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setToolTip(tip)
        btn.clicked.connect(cb)
        return btn

    def _set_path(self, label: QLabel, text: str) -> None:
        label.setText(self._elide_mid(text))
        label.setToolTip(text)

    # ------------------------------------------------------------------
    def _browse(self, title: str, current: str, apply_cb, what: str) -> None:
        chosen = QFileDialog.getExistingDirectory(self, title, current)
        if not chosen:
            return
        apply_cb(chosen)
        self.changed = True
        self._refresh()
        if self._log_cb:
            self._log_cb("ok", f"工作空间已更新：{what} → {chosen}")

    def _reset(self, apply_cb, what: str) -> None:
        apply_cb()
        self.changed = True
        self._refresh()
        if self._log_cb:
            self._log_cb("ok", f"工作空间已恢复默认：{what}")

    # ------------------------------------------------------------------
    # 安装包清理
    # ------------------------------------------------------------------
    def _refresh_cache_label(self) -> None:
        files = [f for f in WS.download_cache_files() if f.exists()]
        if files:
            try:
                total = sum(f.stat().st_size for f in files)
            except OSError:
                total = 0
            self._cache_label.setText(
                f"检测到 {len(files)} 个安装包，共 {human_size(total)}"
                "（各工作空间的 downloads 目录）"
            )
            self._clean_btn.setEnabled(True)
        else:
            self._cache_label.setText("没有可清理的安装包")
            self._clean_btn.setEnabled(False)

    def _clean_downloads(self) -> None:
        files = [f for f in WS.download_cache_files() if f.exists()]
        if not files:
            return
        total = sum(f.stat().st_size for f in files)
        ret = QMessageBox.question(
            self,
            "清理安装包",
            f"确定删除 {len(files)} 个安装包（共 {human_size(total)}）吗？\n\n"
            "已解压安装的组件不受影响；正在下载/安装的任务请先完成。",
        )
        if ret != QMessageBox.Yes:
            return
        ok, freed, failed = 0, 0, 0
        for f in files:
            try:
                freed += f.stat().st_size
                f.unlink()
                ok += 1
            except OSError:
                failed += 1
        if self._log_cb:
            msg = f"已清理 {ok} 个安装包，释放 {human_size(freed)}"
            if failed:
                msg += f"；{failed} 个文件被占用，删除失败（可稍后重试）"
            self._log_cb("ok" if not failed else "warn", msg)
        self._refresh_cache_label()

    # ------------------------------------------------------------------
    def _open_dir(self, path: str) -> None:
        """在系统文件管理器中打开目录（不存在会先创建）。"""
        if open_in_file_manager(path):
            if self._log_cb:
                self._log_cb("ok", f"已打开目录：{path}")
        elif self._log_cb:
            self._log_cb("warn", f"打开目录失败：{path}")

    # ------------------------------------------------------------------
    # 下载镜像
    # ------------------------------------------------------------------
    def _on_mirror_changed(self) -> None:
        mode = self._mirror_combo.currentData() or "auto"
        MIRRORS.mode = mode
        MIRRORS.save()
        self._tmpl_label.setVisible(mode == "custom")
        self._custom_edit.setVisible(mode == "custom")
        if self._log_cb:
            self._log_cb("ok", f"下载通道已切换为：{self._mirror_combo.currentText()}")

    def _on_custom_changed(self, text: str) -> None:
        if MIRRORS.mode != "custom":
            return
        MIRRORS.custom = text.strip()
        MIRRORS.save()

    def _on_parts_changed(self) -> None:
        MIRRORS.parts = int(self._parts_combo.currentData() or 1)
        MIRRORS.save()

    # ------------------------------------------------------------------
    # 安装选项
    # ------------------------------------------------------------------
    def _on_auto_env_changed(self, checked: bool) -> None:
        INSTALL.auto_env = bool(checked)
        INSTALL.save()
        if self._log_cb:
            self._log_cb(
                "ok",
                "环境变量配置：安装后自动写入" if checked
                else "环境变量配置：仅下载解压，需手动点「配置环境变量」",
            )

    # ------------------------------------------------------------------
    # 软件更新
    # ------------------------------------------------------------------
    def _on_auto_clean_changed(self, checked: bool) -> None:
        INSTALL.auto_clean = bool(checked)
        INSTALL.save()
        if self._log_cb:
            self._log_cb(
                "ok",
                "安装包：安装完成后自动清理" if checked
                else "安装包：安装完成后保留，需手动清理",
            )

    # ------------------------------------------------------------------
    # 界面字体
    # ------------------------------------------------------------------
    def _refresh_font_label(self) -> None:
        if UI.system_font:
            self._font_label.setText("当前：系统字体（跟随操作系统界面字体）")
        elif misans_available():
            self._font_label.setText(f"当前：内置 {MISANS_FAMILY}")
        else:
            self._font_label.setText(
                "当前：内置 MiSans（字体文件缺失，已回退系统字体）")

    def _on_sysfont_changed(self, checked: bool) -> None:
        UI.system_font = bool(checked)
        UI.save()
        # 立即换字体：QApplication.setFont 会广播给所有未单独设置字体的控件
        app = QApplication.instance()
        family = apply_app_font(app, UI.system_font) if app else ""
        self._refresh_font_label()
        if self._log_cb:
            self._log_cb(
                "ok",
                f"界面字体已切换为：{'系统字体' if checked else '内置 MiSans'}"
                f"（{family or '未指定'}）",
            )

    def _start_update_check(self) -> None:
        self._update_btn.setEnabled(False)
        self._update_label.setText("正在检查更新…")
        self._update_worker = UpdateCheckWorker(parent=self)
        self._update_worker.done.connect(self._on_update_done)
        self._update_worker.failed.connect(self._on_update_failed)
        # 证书降级等过程提示转到主窗口日志
        self._update_worker.note.connect(
            lambda msg: self._log_cb and self._log_cb("info", msg))
        self._update_worker.start()

    def _on_update_done(self, info) -> None:
        self._update_btn.setEnabled(True)
        latest = info.version
        if is_newer(latest):
            self._update_label.setText(
                f"发现新版本 {latest}（当前 {APP_VERSION}"
                f"{'，发布于 ' + info.published if info.published else ''}）"
            )
            self._show_update_dialog(info)
            if self._log_cb:
                self._log_cb("ok", f"发现新版本 {latest}，可在发布页下载更新。")
        else:
            self._update_label.setText(f"已是最新版本（{APP_VERSION}）")
            if self._log_cb:
                self._log_cb("ok", f"检查更新：当前 {APP_VERSION} 已是最新版本。")

    def _on_update_failed(self, reason: str) -> None:
        self._update_btn.setEnabled(True)
        self._update_label.setText(f"检查更新失败：{reason}")
        if self._log_cb:
            self._log_cb("warn", f"检查更新失败：{reason}")

    def _show_update_dialog(self, info) -> None:
        """有新版本时弹出说明，并提供「前往下载」跳转发布页。"""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("发现新版本")
        box.setText(f"新版本 {info.version} 已发布（当前 {APP_VERSION}）")
        detail = info.notes or "（该版本未提供更新说明）"
        if info.published:
            detail = f"发布于 {info.published}\n\n{detail}"
        box.setInformativeText(detail)
        goto = box.addButton("前往下载", QMessageBox.AcceptRole)
        box.addButton("以后再说", QMessageBox.RejectRole)
        box.setDefaultButton(goto)
        box.exec()
        if box.clickedButton() is goto:
            QDesktopServices.openUrl(QUrl(info.url or RELEASES_LATEST_URL))

    def _start_probe(self) -> None:
        self._probe_btn.setEnabled(False)
        self._probe_label.setVisible(True)
        self._probe_label.setText("测速中…（各通道抽样下载 512 KB）")
        self._probe_worker = MirrorProbeWorker(parent=self)
        self._probe_worker.done.connect(self._on_probe_done)
        self._probe_worker.start()

    def _on_probe_done(self, results) -> None:
        lines = []
        for _mid, name, speed in results:
            lines.append(f"{name}：{int(speed)} KB/s" if speed > 0 else f"{name}：不可用")
        self._probe_label.setText("\n".join(lines))
        self._probe_btn.setEnabled(True)

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        self._set_path(self._global_label,
                       WS.global_ws or f"内置默认（{CONFIG_DIR}）")
        for cat, lab in self._cat_labels.items():
            self._set_path(lab, WS.categories.get(cat) or "跟随全局")
        # 没有任何组件自定义目录时，整组隐藏，不占纵向空间
        self._override_grp.setVisible(bool(WS.components))
        # 重建覆盖清单
        while self._override_box.count():
            item = self._override_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not WS.components:
            empty = QLabel("暂无组件自定义目录。")
            empty.setObjectName("pathMuted")
            self._override_box.addWidget(empty)
        for key, path in sorted(WS.components.items()):
            row = QHBoxLayout()
            name = QLabel(self._names.get(key, key))
            name.setObjectName("pathName")
            row.addWidget(name)
            lab = QLabel(self._elide_mid(path))
            lab.setObjectName("pathMuted")
            lab.setToolTip(path)
            row.addWidget(lab, stretch=1)
            btn = QPushButton("清除")
            btn.setObjectName("secondaryBtn")
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(lambda _=False, k=key: self._reset(
                lambda k=k: WS.set_component(k, None),
                f"组件「{self._names.get(k, k)}」自定义目录"))
            row.addWidget(btn)
            wrap = QWidget()
            wrap.setLayout(row)
            self._override_box.addWidget(wrap)
