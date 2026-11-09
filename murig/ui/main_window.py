# -*- coding: utf-8 -*-
"""主窗口（无边框自定义标题栏）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QEvent, QPoint, QSize, Qt
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (
 QDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QPushButton, QScrollArea,
    QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from ..catalog.registry import FETCHERS, VersionFetchWorker, build_components
from ..core.models import Component
from ..core.constants import (
    APP_NAME, APP_VERSION, CATEGORIES, CATEGORY_ORDER, CONFIG_DIR,
    CURRENT_OS, MACHINE, SETTINGS_FILE,
)
from ..core.utils import open_in_file_manager
from ..core.workspace import WS
from .dialogs import AboutDialog, WorkspaceDialog
from .icons import (
    BAR_FG, about_icon, close_icon, folder_icon,
    maximize_icon, minimize_icon, refresh_icon, restore_icon, settings_icon,
)
from .widgets import ComponentCard


def _enable_dwm_round_corners(win: QMainWindow) -> bool:
    """Windows 11 (build 22000+) 上启用 DWM 原生圆角窗口，返回是否成功。

    原生圆角由系统合成器裁剪，边缘干净无白边，且窗口保持不透明，
    文字可以继续使用 ClearType 亚像素抗锯齿（透明窗口会被强制灰度）。
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        pref = ctypes.c_int(DWMWCP_ROUND)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(win.winId()), DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref), ctypes.sizeof(pref),
        )
        return res == 0
    except Exception:
        return False


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
        # Windows 11：DWM 原生圆角 + 不透明窗口（保留 ClearType 亚像素抗锯齿）；
        # 旧系统回退：透明窗口 + QSS 圆角（圆角处透出桌面）
        self._native_round = _enable_dwm_round_corners(self)
        if not self._native_round:
            self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.components = build_components()
        self._drag_pos: Optional[QPoint] = None
        self._fetch_workers: List[VersionFetchWorker] = []
        self._fetch_pending: int = 0
        # 当前选中的分类 key；搜索关键字直接从搜索框读取
        self._current_category: str = "all"

        self._build_ui()
        self._load_settings()
        self.refresh_status_bar()
        if WS.migrated:
            self._append_log(
                "info",
                f"设置已从旧工作目录迁移到 {SETTINGS_FILE}（旧文件保留未删除）",
            )
        self._start_fetch_versions()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralRoot")
        # square=true（DWM 原生圆角或最大化）时 QSS 会取消 QSS 圆角
        central.setProperty("square", self._native_round)
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
        tb.addWidget(title_label)
        tb.addStretch(1)

        # 关于我们（图标为代码绘制的线性图标，统一视觉、避免 emoji 锯齿）
        self.btn_about = QPushButton("关于我们")
        self.btn_about.setIcon(about_icon(15))
        self.btn_about.setIconSize(QSize(15, 15))
        self.btn_about.setObjectName("iconBtn")
        self.btn_about.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_about.setToolTip("了解我们 & 联系方式")
        self.btn_about.clicked.connect(self._on_about_clicked)
        tb.addWidget(self.btn_about)

        # 刷新版本列表按钮
        self.btn_refresh = QPushButton("刷新版本")
        self.btn_refresh.setIcon(refresh_icon(15))
        self.btn_refresh.setIconSize(QSize(15, 15))
        self.btn_refresh.setObjectName("iconBtn")
        self.btn_refresh.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_refresh.setToolTip("重新从官网抓取所有组件的可用版本列表")
        self.btn_refresh.clicked.connect(self._start_fetch_versions)
        tb.addWidget(self.btn_refresh)

        # 设置：工作空间目录 / 下载通道 / 安装选项
        self.btn_workspace = QPushButton("设置")
        self.btn_workspace.setIcon(settings_icon(14, BAR_FG))
        self.btn_workspace.setIconSize(QSize(14, 14))
        self.btn_workspace.setObjectName("iconBtn")
        self.btn_workspace.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_workspace.setToolTip("设置安装目录、下载通道与安装选项")
        self.btn_workspace.clicked.connect(self._on_workspace_clicked)
        tb.addWidget(self.btn_workspace)

        # 打开工作空间目录（系统文件管理器）
        self.btn_open_dir = QPushButton("打开目录")
        self.btn_open_dir.setIcon(folder_icon(14, BAR_FG))
        self.btn_open_dir.setIconSize(QSize(14, 14))
        self.btn_open_dir.setObjectName("iconBtn")
        self.btn_open_dir.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_open_dir.setToolTip("在系统文件管理器中打开当前工作空间目录")
        self.btn_open_dir.clicked.connect(self._on_open_dir_clicked)
        tb.addWidget(self.btn_open_dir)

        # 窗口控制按钮：统一固定尺寸 + 矢量图标，保证三者一致
        ctrl_size = QSize(44, 30)
        icon_size = QSize(14, 14)

        self.btn_min = QPushButton()
        self.btn_min.setIcon(minimize_icon(14))
        self.btn_min.setIconSize(icon_size)
        self.btn_min.setFixedSize(ctrl_size)
        self.btn_min.setObjectName("ctrlBtn")
        self.btn_min.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_min.clicked.connect(self.showMinimized)
        tb.addWidget(self.btn_min)

        self.btn_max = QPushButton()
        self.btn_max.setIcon(maximize_icon(14))
        self.btn_max.setIconSize(icon_size)
        self.btn_max.setFixedSize(ctrl_size)
        self.btn_max.setObjectName("ctrlBtn")
        self.btn_max.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_max.clicked.connect(self._toggle_max)
        tb.addWidget(self.btn_max)

        self.btn_close = QPushButton()
        self.btn_close.setIcon(close_icon(14))
        self.btn_close.setIconSize(icon_size)
        self.btn_close.setFixedSize(ctrl_size)
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

        # 分类筛选：一排胶囊合并为「分类：全部」下拉菜单，点开选择分类
        self.btn_category = QPushButton("分类：全部")
        self.btn_category.setObjectName("categoryChip")
        self.btn_category.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_category.setFixedHeight(34)
        self.btn_category.setToolTip("选择要显示的组件分类")
        self.category_menu = QMenu(self.btn_category)
        self.category_actions: Dict[str, QAction] = {}
        for cat in ["all", *CATEGORY_ORDER]:
            act = QAction(CATEGORIES[cat], self.category_menu)
            act.setCheckable(True)
            act.setChecked(cat == "all")
            act.triggered.connect(lambda _=False, c=cat: self._on_category_chosen(c))
            self.category_menu.addAction(act)
            self.category_actions[cat] = act
        self.btn_category.setMenu(self.category_menu)
        fb.addWidget(self.btn_category)
        fb.addSpacing(10)

        self.search_box = QLineEdit()
        self.search_box.setObjectName("searchBox")
        self.search_box.setPlaceholderText("搜索软件名 / 别名 / 分类名，例如 redis、数据库、kafka…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedHeight(34)
        self.search_box.textChanged.connect(self._apply_filter)
        fb.addWidget(self.search_box, stretch=1)

        # 中部内容容器：渐变背景只画在这里（不画在 centralRoot 上）。
        # 回退模式下圆角缺口处不会露出浅色背景的白边，缺口只透出桌面。
        self.content_area = QFrame()
        self.content_area.setObjectName("contentArea")
        inner = QVBoxLayout(self.content_area)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        inner.addWidget(self.filter_bar)

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
        inner.addWidget(body, 1)
        outer.addWidget(self.content_area, 1)

        # 底部状态条：左侧系统信息，右侧版本号
        self.status_bar = QFrame()
        self.status_bar.setObjectName("statusBar")
        self.status_bar.setFixedHeight(26)
        sb = QHBoxLayout(self.status_bar)
        sb.setContentsMargins(14, 0, 14, 0)
        sb.setSpacing(0)
        self.status_left = QLabel()
        self.status_left.setStyleSheet("color:#9aa0ad;background:none;border:none;")
        sb.addWidget(self.status_left)
        sb.addStretch(1)
        status_version = QLabel(f"版本号 {APP_VERSION}")
        status_version.setStyleSheet("color:#9aa0ad;background:none;border:none;")
        sb.addWidget(status_version)
        outer.addWidget(self.status_bar)


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
        else:
            self.showMaximized()

    def changeEvent(self, event) -> None:  # noqa: N802
        """窗口最大化/还原时同步按钮图标，并切换圆角（最大化时直角）。"""
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            if hasattr(self, "btn_max"):
                self.btn_max.setIcon(
                    restore_icon(14) if self.isMaximized() else maximize_icon(14)
                )
            maximized = self.isMaximized()
            central = self.centralWidget()
            if central is not None:
                # 最大化时取消 QSS 圆角（原生 DWM 圆角由系统自动变直角）
                central.setProperty("square", self._native_round or maximized)
                for w in (central, self.title_bar, self.status_bar):
                    w.style().unpolish(w)
                    w.style().polish(w)

    # ------------------------------------------------------------------
    # 分类筛选 & 搜索
    # ------------------------------------------------------------------
    def _on_category_chosen(self, cat: str) -> None:
        """选择分类：更新下拉按钮文字与勾选态并重新过滤卡片。"""
        self._current_category = cat
        for c, act in self.category_actions.items():
            act.setChecked(c == cat)
        self.btn_category.setText(f"分类：{CATEGORIES[cat]}")
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
            self.btn_refresh.setText("抓取中…")
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
            self.btn_refresh.setText("刷新版本")
            self._append_log("info", "版本列表获取完成。")


    # ------------------------------------------------------------------
    def _on_about_clicked(self) -> None:
        AboutDialog(self).exec()

    # ------------------------------------------------------------------
    def _on_workspace_clicked(self) -> None:
        names = {c.key: c.display_name for c in self.components}
        dlg = WorkspaceDialog(self, self._append_log, names)
        if dlg.exec() == QDialog.Accepted:
            # 有过修改：刷新全部卡片徽章与安装位置提示
            for card in self.cards:
                card._detect_status()
            self.refresh_status_bar()

    # ------------------------------------------------------------------
    def _on_open_dir_clicked(self) -> None:
        root = Path(WS.global_ws) if WS.global_ws else CONFIG_DIR
        if open_in_file_manager(root):
            self._append_log("ok", f"已打开工作空间目录：{root}")
        else:
            self._append_log("warn", f"打开目录失败：{root}")

    # ------------------------------------------------------------------
    def refresh_status_bar(self) -> None:
        self.status_left.setText(
            f"系统：{CURRENT_OS} ({MACHINE})   工作目录：{WS.global_ws or CONFIG_DIR}"
            "（可在「设置」修改）"
        )

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
        if not SETTINGS_FILE.exists():
            return
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
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
        # 与 workspace 段同存于 ~/.murig/config.json
        WS.save({
            card.component.key: card.version_combo.currentText()
            for card in self.cards
        })

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        self._save_settings()
        super().closeEvent(event)
