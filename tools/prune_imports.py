# -*- coding: utf-8 -*-
"""清理各模块中未使用的 import（依据 pyflakes 报告）。

用法： python tools/prune_imports.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile(r"^(.+?):(\d+):\d+: '([^']+)' imported but unused")


def collect() -> list[tuple[str, int, str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "pyflakes", "murig"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    hits: list[tuple[str, int, str]] = []
    for line in (proc.stdout or "").splitlines():
        m = PATTERN.match(line)
        if m:
            hits.append((m.group(1), int(m.group(2)), m.group(3).split(".")[-1]))
    return hits


def prune(path: Path, lineno: int, name: str) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines()
    idx = lineno - 1
    if idx >= len(lines):
        return False
    stmt = lines[idx]
    stripped = stmt.strip()

    # 单条 import 且只导入这一个名字 → 整行删除
    if not stmt.rstrip().endswith(",") and "(" not in stmt:
        if re.fullmatch(rf"(from\s+[\w.]+\s+import\s+{name}|import\s+{name})", stripped):
            del lines[idx]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True

    # 括号内的多行导入 → 删除该名字（含尾随逗号）
    start = idx
    while start > 0 and "import" not in lines[start - 1]:
        start -= 1
    if "(" not in lines[start]:
        return False
    end = start
    while end < len(lines) and ")" not in lines[end]:
        end += 1
    for i in range(start, min(end + 1, len(lines))):
        if re.search(rf"\b{re.escape(name)}\b", lines[i]):
            new = re.sub(rf"\s*\b{re.escape(name)}\b\s*,?", "", lines[i])
            if new.strip() in ("", ")"):
                del lines[i]
            else:
                lines[i] = new
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    return False


def main() -> None:
    # 先整体收集，再逐条处理（每次删除都会让行号失效，故按文件倒序处理）
    hits = collect()
    by_file: dict[str, list[tuple[int, str]]] = {}
    for f, ln, name in hits:
        by_file.setdefault(f, []).append((ln, name))

    for f, items in by_file.items():
        path = ROOT / f
        for lineno, name in sorted(items, reverse=True):
            if not path.exists():
                continue
            ok = prune(path, lineno, name)
            print(f"[{'prune' if ok else 'skip '}] {f}:{lineno} {name}")
        # 行号会漂移，重新跑一轮直到稳定
        for _ in range(6):
            remaining = [(f, ln, n) for f, ln, n in collect() if f == f]
            if not remaining:
                break
            for _, lineno, name in sorted([(a, b, c) for a, b, c in remaining], reverse=True):
                prune(path, lineno, name)


if __name__ == "__main__":
    main()
