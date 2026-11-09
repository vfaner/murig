# -*- coding: utf-8 -*-
"""断点续传状态：记录每个分块已写入的字节，支持中断后继续下载。

状态保存在 <目标文件名>.part.json（与目标文件同目录），字段：
  url/total/etag/last_modified —— 用于判断远端文件是否被换过
  mode(plain|chunked)/parts    —— 分块方式变了就无法复用旧进度
  chunks                       —— [{"start","end","done"}]，done 是该块已写入字节

未完成的 .part 文件会一直保留：下次下载同一目标时会先校验再续传，
用户取消/断网都不会白下。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ResumeState:
    url: str
    total: int
    mode: str = "chunked"          # chunked（并行分块） / plain（单线程流式）
    parts: int = 1
    etag: str = ""
    last_modified: str = ""
    chunks: List[Dict] = field(default_factory=list)

    # ------------------------------------------------------------------
    @staticmethod
    def state_path(dest: Path) -> Path:
        return dest.with_suffix(dest.suffix + ".part.json")

    @staticmethod
    def part_path(dest: Path) -> Path:
        return dest.with_suffix(dest.suffix + ".part")

    # ------------------------------------------------------------------
    def downloaded(self) -> int:
        """已写入的字节总数。"""
        if self.mode == "plain":
            return int(self.chunks[0]["done"]) if self.chunks else 0
        return sum(int(c.get("done", 0)) for c in self.chunks)

    def remaining_ranges(self) -> List[tuple]:
        """chunked 模式：返回各块【尚未下载】的区间 [(start, end)]。"""
        out = []
        for c in self.chunks:
            start = int(c["start"]) + int(c.get("done", 0))
            end = int(c["end"])
            if start <= end:
                out.append((start, end))
        return out

    def mark(self, chunk_index: int, start: int, end: int) -> None:
        """记录某块已写到 start（即 done = start - chunk.start）。"""
        if 0 <= chunk_index < len(self.chunks):
            self.chunks[chunk_index]["done"] = start - int(self.chunks[chunk_index]["start"])

    def matches(self, total: int, etag: str = "", last_modified: str = "") -> bool:
        """远端文件是否还是原来那个（大小/ETag/Last-Modified 校验）。"""
        if self.total != total:
            return False
        if self.etag and etag and self.etag != etag:
            return False
        if self.last_modified and last_modified and self.last_modified != last_modified:
            return False
        return True

    # ------------------------------------------------------------------
    def save(self, dest: Path) -> None:
        try:
            self.state_path(dest).write_text(
                json.dumps({
                    "url": self.url,
                    "total": self.total,
                    "mode": self.mode,
                    "parts": self.parts,
                    "etag": self.etag,
                    "last_modified": self.last_modified,
                    "chunks": self.chunks,
                }, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass  # 状态写失败不影响下载本身，只是这次不能续传

    @classmethod
    def load(cls, dest: Path) -> Optional["ResumeState"]:
        path = cls.state_path(dest)
        if not path.exists() or not cls.part_path(dest).exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                url=data.get("url", ""),
                total=int(data.get("total", 0)),
                mode=data.get("mode", "chunked"),
                parts=int(data.get("parts", 1)),
                etag=data.get("etag", ""),
                last_modified=data.get("last_modified", ""),
                chunks=list(data.get("chunks") or []),
            )
        except Exception:
            return None

    @staticmethod
    def clear(dest: Path) -> None:
        """下载完成：删掉状态文件（.part 已被 rename 成目标文件）。"""
        try:
            ResumeState.state_path(dest).unlink(missing_ok=True)
        except Exception:
            pass

    @staticmethod
    def discard(dest: Path) -> None:
        """放弃进度：状态与半成品一起删除。"""
        try:
            ResumeState.state_path(dest).unlink(missing_ok=True)
            ResumeState.part_path(dest).unlink(missing_ok=True)
        except Exception:
            pass
