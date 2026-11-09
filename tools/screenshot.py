# -*- coding: utf-8 -*-
"""无头截图：把主窗口与对话框渲染成 PNG，便于人工核对视觉效果。

用法： python tools/screenshot.py [输出目录]
产物： murig-main.png / murig-about.png / murig-donate.png / murig-workspace.png
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
from murig.ui.theme import apply_theme  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "tools" / "shots"


def run() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    apply_theme(app)

    win = MainWindow()
    win.resize(1080, 720)
    win.show()
    app.processEvents()
    win.grab().save(str(OUT / "murig-main.png"))

    for name, dlg in (
        ("about", AboutDialog(win)),
        ("workspace", WorkspaceDialog(win, lambda *a: None, {})),
    ):
        dlg.show()
        app.processEvents()
        dlg.grab().save(str(OUT / f"murig-{name}.png"))
        print(f"[shot] murig-{name}.png")

    print(f"[shot] 输出目录：{OUT}")
    QTimer.singleShot(200, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(run())
