# -*- coding: utf-8 -*-
"""断点续传测试：下载中途取消 -> 再次下载从断点继续 -> 校验文件完整。

用法：
    python tools/test_resume.py [url] [parts]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from murig.core.http import get as http_get  # noqa: E402
from murig.core.mirrors import MIRRORS, PROBE_URL  # noqa: E402
from murig.core.resume import ResumeState  # noqa: E402
from murig.core.workers import DownloadWorker  # noqa: E402
from murig.core.utils import human_size  # noqa: E402

# 第一阶段下载多少秒后取消（太短的话数据还没开始写入，测不出续传）
CANCEL_AFTER = 8.0


def expected_size(url: str) -> int:
    r = http_get(url, timeout=30, stream=True)
    with r:
        return int(r.headers.get("Content-Length", 0) or 0)


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else PROBE_URL
    parts = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    cancel_after = float(sys.argv[3]) if len(sys.argv) > 3 else CANCEL_AFTER
    MIRRORS.parts = parts
    app = QCoreApplication(sys.argv)

    expect = expected_size(url)
    dest = Path("_resume_test.zip")
    ResumeState.discard(dest)
    dest.unlink(missing_ok=True)
    print(f"目标大小：{expect} 字节，并行段数：{parts}\n")

    # ---- 阶段 1：下载一段时间后取消 ----
    w = DownloadWorker(url, dest)
    w.log.connect(lambda lv, m: print(f"  [{lv}] {m}"))
    QTimer.singleShot(int(cancel_after * 1000), w.cancel)
    w.start()
    while w.isRunning():
        app.processEvents()
        time.sleep(0.05)

    state = ResumeState.load(dest)
    part = ResumeState.part_path(dest)
    if state is None or not part.exists():
        print("[FAIL] 取消后没有留下可续传的进度")
        return 1
    done = state.downloaded()
    print(f"\n已保存进度：{human_size(done)} / {human_size(expect)}（{done / expect:.0%}）")
    print(f"状态文件：{ResumeState.state_path(dest)}")
    if done <= 0:
        print("[FAIL] 进度为 0，说明还没开始写入就被取消，请调大取消时间")
        return 1

    # ---- 阶段 2：重新下载，应续传 ----
    w2 = DownloadWorker(url, dest)
    w2.log.connect(lambda lv, m: print(f"  [{lv}] {m}"))
    t = time.time()
    w2.run()  # 同步跑，便于计时
    dt = time.time() - t

    ok = dest.exists() and dest.stat().st_size == expect
    got = dest.stat().st_size if dest.exists() else 0
    leftover = ResumeState.state_path(dest).exists() or part.exists()
    print(f"\n续传完成：{dt:.1f}s  size={got}/{expect}  {'OK' if ok else 'MISMATCH'}")
    print(f"临时文件已清理：{'否（有残留）' if leftover else '是'}")

    # 内容校验：分块错位时大小仍可能对，但 zip 内部 CRC 会失败
    crc_ok = True
    if ok:
        import zipfile
        try:
            bad = zipfile.ZipFile(dest).testzip()
            crc_ok = bad is None
            print(f"内容校验（zip CRC）：{'通过' if crc_ok else '损坏：' + str(bad)}")
        except Exception as exc:
            crc_ok = False
            print(f"内容校验（zip CRC）：无法校验（{exc}）")

    dest.unlink(missing_ok=True)
    return 0 if ok and crc_ok and not leftover else 1


if __name__ == "__main__":
    sys.exit(main())
