# -*- coding: utf-8 -*-
"""镜像测速自检：确认各下载通道是否可用、速度如何。

用法：
    python tools/check_mirrors.py [url]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from murig.core.mirrors import MIRRORS, PROBE_URL  # noqa: E402
from murig.core.workers import DownloadWorker  # noqa: E402


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else PROBE_URL
    print(f"测速目标：{url}\n")
    for _mid, name, speed in MIRRORS.probe(url):
        print(f"  {name:20s} {'不可用' if speed <= 0 else f'{int(speed):8d} KB/s'}")

    print("\n当前设置：mode=%s custom=%s fastest=%s" % (
        MIRRORS.mode, MIRRORS.custom or "-", MIRRORS.fastest or "-"))
    w = DownloadWorker(url, Path("_probe_tmp.bin"))
    print("下载通道顺序：")
    for label, u in w._channels():
        print(f"  - {label}: {u}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
