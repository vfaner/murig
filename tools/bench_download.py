# -*- coding: utf-8 -*-
"""分块下载实测：比较并行段数对速度的影响，并校验文件完整性。

用法：
    python tools/bench_download.py [url] [parts...]
例：
    python tools/bench_download.py https://github.com/.../x.zip 1 4
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from murig.core.http import get as http_get  # noqa: E402
from murig.core.mirrors import MIRRORS, PROBE_URL  # noqa: E402
from murig.core.workers import DownloadWorker  # noqa: E402


def expected_size(url: str) -> int:
    r = http_get(url, timeout=30, stream=True)
    with r:
        return int(r.headers.get("Content-Length", 0) or 0)


def bench(url: str, parts: int, expect: int) -> None:
    MIRRORS.parts = parts
    dest = Path(f"_bench_{parts}.bin")
    dest.unlink(missing_ok=True)
    w = DownloadWorker(url, dest)
    w.log.connect(lambda lv, m: print(f"  [{lv}] {m}"))
    t = time.time()
    w.run()
    dt = time.time() - t
    ok = dest.exists() and (expect == 0 or dest.stat().st_size == expect)
    got = dest.stat().st_size if dest.exists() else 0
    print(f"parts={parts}: {dt:.1f}s  {got/1024/dt:,.0f} KB/s  "
          f"size={got}/{expect} {'OK' if ok else 'MISMATCH'}")
    dest.unlink(missing_ok=True)


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else PROBE_URL
    parts_list = [int(x) for x in sys.argv[2:]] or [1, 4]
    app = QCoreApplication(sys.argv)  # noqa: F841
    expect = expected_size(url)
    print(f"目标：{url}\n大小：{expect} 字节\n")
    for p in parts_list:
        bench(url, p, expect)
    return 0


if __name__ == "__main__":
    sys.exit(main())
