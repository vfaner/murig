# -*- coding: utf-8 -*-
"""无头冒烟测试：用 offscreen 平台真实构造主窗口与所有对话框。

用法： python tools/smoke.py
用于验证重构后没有 import / 属性 / 布局 / 样式层面的运行时错误。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from murig.ui.dialogs import AboutDialog, WorkspaceDialog  # noqa: E402
from murig.ui.main_window import MainWindow  # noqa: E402
from murig.ui.theme import apply_theme, load_stylesheet, stylesheet_path  # noqa: E402


def check_stylesheet() -> None:
    qss = load_stylesheet()
    path = stylesheet_path()
    if not path.exists():
        raise SystemExit(f"[smoke] 主题文件缺失：{path}")
    if qss.count("{") != qss.count("}"):
        raise SystemExit(
            f"[smoke] 主题括号不平衡：{{={qss.count('{')} }}={qss.count('}')}"
        )
    print(f"[smoke] 主题已加载：{path.name}（{len(qss)} 字符）")


def run() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    check_stylesheet()

    win = MainWindow()
    win.show()
    print(f"[smoke] 主窗口已构造，组件卡片 {len(win.cards)} 个")

    for cls in (AboutDialog, WorkspaceDialog):
        dlg = cls(win) if cls is not WorkspaceDialog else cls(win, lambda *a: None, {})
        dlg.show()
        print(f"[smoke] 对话框已构造：{cls.__name__}")

    QTimer.singleShot(1500, app.quit)
    app.exec()
    print("[smoke] 事件循环正常退出")
    return 0


if __name__ == "__main__":
    sys.exit(run())
