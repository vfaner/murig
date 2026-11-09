# -*- coding: utf-8 -*-
"""后台线程：文件下载与外部命令执行。"""

from __future__ import annotations

import math
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QThread, Signal

from .constants import CURRENT_OS
from .http import get as http_get
from .mirrors import DIRECT, MIRRORS, PROBE_URL
from .resume import ResumeState
from .updates import fetch_latest
from .utils import ensure_dir, human_size


# 进程内记录「假续传」的地址：返回 206 但实际给全量内容。
# 下次对同一主机直接完整下载，避免先白下一次再重来
_BAD_RESUME: set = set()


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


class RangeUnsupported(Exception):
    """服务端不支持 Range（未返回 206），分块/续传都不可用。"""


class FileMeta(NamedTuple):
    """远端文件信息，用于判断是否可续传。"""

    url: str            # 重定向后的真实地址
    total: int          # 文件总大小（0 表示未知）
    etag: str
    last_modified: str
    supports_range: bool


# ---------------------------------------------------------------------------
# 下载线程
# ---------------------------------------------------------------------------
class DownloadWorker(QThread):
    """使用 requests 流式下载文件的后台线程。"""

    progress = Signal(int, int)  # (downloaded_bytes, total_bytes)
    log = Signal(str, str)  # (level, message)  level in {"info","warn","error","ok"}
    finished_ok = Signal(str)  # 保存的本地文件绝对路径
    finished_fail = Signal(str)  # 错误信息

    # 小于这个体积就不值得分块（握手开销大于收益）
    MIN_CHUNKED_SIZE = 4 * 1024 * 1024

    def __init__(self, url: str, dest: Path, headers: Optional[Dict[str, str]] = None,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.url = url
        self.dest = dest
        self.headers = headers or None
        self._cancel = False
        self._done = 0
        self._lock = threading.Lock()
        self._responses: List = []

    def cancel(self) -> None:
        self._cancel = True
        # 正在阻塞读取的响应直接断开，避免取消后还要等超时
        for r in list(self._responses):
            try:
                r.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _emit_cancelled(self) -> None:
        self.log.emit("warn", "已取消下载。")
        self.finished_fail.emit("用户取消")

    # ------------------------------------------------------------------
    def _channels(self) -> List[Tuple[str, str]]:
        """按优先级给出下载通道 [(名称, URL)]：镜像在前，直连兜底。"""
        mirrors = MIRRORS.candidates(self.url)
        if MIRRORS.mode in ("auto", "") and not MIRRORS.fastest_for(self.url):
            # 首次使用：对真实 URL 抽样测速，自动挑最快的通道
            best = MIRRORS.auto_select(
                self.url, on_note=lambda lv, m: self.log.emit(lv, m)
            )
            if best is not None:
                mirrors = [best, DIRECT]
        return [
            (f"镜像 {m.name}" if m.id != "direct" else "直连", m.url_for(self.url))
            for m in mirrors
        ]

    def _download(self, url: str, note_prefix: str) -> bool:
        """从指定通道下载。

        返回 True 表示成功；False 表示被用户取消（进度已保存，可续传）。
        失败则抛异常：Range 不可用时会清掉进度并回退单线程；网络类错误
        保留进度，由 run() 切换到下一个通道继续（同样从断点续传）。
        """
        self.log.emit("info", f"开始下载（{note_prefix}）：{url}")
        ensure_dir(self.dest.parent)
        tmp = ResumeState.part_path(self.dest)

        meta = self._probe_meta(url)
        state = self._validate_resume(ResumeState.load(self.dest), meta)

        if MIRRORS.parts > 1 and meta is not None and meta.supports_range:
            if meta.total >= self.MIN_CHUNKED_SIZE:
                try:
                    if self._download_chunked(meta, tmp, MIRRORS.parts, state):
                        tmp.replace(self.dest)
                        ResumeState.clear(self.dest)
                        self._emit_ok()
                        return True
                    return False  # 已取消，进度由 _download_chunked 保存
                except RangeUnsupported:
                    # 服务端不支持分块：半成品无法复用，回退单线程重下
                    self.log.emit("warn", "服务端不支持分块，回退单线程下载。")
                    ResumeState.discard(self.dest)
                    state = None
                # 其它异常直接向上抛：进度已保存，由 run() 切通道继续续传
        return self._download_plain(url, tmp, meta, state)

    # ------------------------------------------------------------------
    def _probe_meta(self, url: str) -> Optional[FileMeta]:
        """探测远端文件信息（大小 / ETag / 是否支持 Range）。"""
        try:
            r = http_get(
                url, timeout=30, headers=self.headers, stream=True,
                allow_redirects=True,
                on_note=lambda m: self.log.emit("warn", m),
            )
            with r:
                return FileMeta(
                    url=r.url,
                    total=int(r.headers.get("Content-Length", 0) or 0),
                    etag=r.headers.get("ETag", ""),
                    last_modified=r.headers.get("Last-Modified", ""),
                    supports_range=r.headers.get("Accept-Ranges", "").lower() == "bytes",
                )
        except Exception as exc:  # noqa: BLE001
            self.log.emit("warn", f"获取文件信息失败（{exc}），改用单线程下载。")
            return None

    def _validate_resume(self, state: Optional[ResumeState],
                         meta: Optional[FileMeta]) -> Optional[ResumeState]:
        """校验已有进度能否复用；不能复用就丢弃（文件变了 / 段数变了）。"""
        if state is None or meta is None or meta.total <= 0:
            return None
        if not state.matches(meta.total, meta.etag, meta.last_modified):
            self.log.emit("warn", "远端文件已变化，重新下载。")
            ResumeState.discard(self.dest)
            return None
        if state.mode == "chunked" and (state.parts != MIRRORS.parts or not state.chunks):
            self.log.emit("warn", "并行段数已变更，重新下载。")
            ResumeState.discard(self.dest)
            return None
        done = state.downloaded()
        if done <= 0 or done >= meta.total:
            ResumeState.discard(self.dest)
            return None
        self.log.emit(
            "info", f"发现未完成的下载，从 {human_size(done)} / {human_size(meta.total)} 继续。")
        return state

    # ------------------------------------------------------------------
    def _download_chunked(self, meta: FileMeta, tmp: Path, parts: int,
                          state: Optional[ResumeState]) -> bool:
        """多线程分块下载：预分配文件，各块按 Range 写自己的区间。

        支持断点续传：state 里记录了每块已写入字节，只请求未完成的区间。
        成功返回 True；取消返回 False（进度已保存）；服务端不支持 Range 抛
        RangeUnsupported。
        """
        total = meta.total
        if state is not None and state.mode == "chunked" and state.chunks:
            chunks = state.chunks
            # 补齐文件长度（.part 可能被外部动过），已有内容保持不动
            if not tmp.exists() or tmp.stat().st_size < total:
                with open(tmp, "ab") as f:
                    f.truncate(total)
        else:
            size = math.ceil(total / parts)
            chunks = [
                {"start": i * size, "end": min(total, (i + 1) * size) - 1, "done": 0}
                for i in range(parts)
            ]
            chunks = [c for c in chunks if c["start"] <= c["end"]]
            with open(tmp, "wb") as f:
                f.truncate(total)  # 预分配，各块直接 seek 写入，无需事后合并
            state = ResumeState(url=meta.url, total=total, mode="chunked",
                                parts=parts, etag=meta.etag,
                                last_modified=meta.last_modified, chunks=chunks)

        jobs = []  # [(块下标, 起始, 结束)]：只排未完成的区间
        for i, c in enumerate(chunks):
            start = int(c["start"]) + int(c.get("done", 0))
            end = int(c["end"])
            if start <= end:
                jobs.append((i, start, end))
        self.log.emit(
            "info",
            f"并行分块下载：{len(jobs)} 段待下载 / 共 {len(chunks)} 段"
            f"（已完成 {human_size(state.downloaded())}）",
        )
        self._done = state.downloaded()

        def worker(index: int, start: int, end: int) -> None:
            headers = dict(self.headers or {})
            headers["Range"] = f"bytes={start}-{end}"
            # 不接受压缩：解压后的长度与 Content-Length 对不上会破坏块偏移
            headers.setdefault("Accept-Encoding", "identity")
            r = http_get(
                meta.url, timeout=60, headers=headers, stream=True,
                allow_redirects=True,
                on_note=lambda m: self.log.emit("warn", m),
            )
            self._responses.append(r)
            try:
                with r:
                    # 只接受 206：服务端不支持 Range 时会返回 200 全量，按偏移
                    # 写进去会把文件写坏，这种情况必须回退单线程
                    if r.status_code != 206:
                        raise RangeUnsupported(
                            f"服务端不支持分块（状态码 {r.status_code}）")
                    with open(tmp, "r+b") as f:
                        f.seek(start)
                        for chunk in r.iter_content(chunk_size=64 * 1024):
                            if self._cancel:
                                return
                            if not chunk:
                                continue
                            # 超出本块末尾的部分一律丢弃，避免污染下一块
                            left = end - f.tell() + 1
                            if left <= 0:
                                break
                            if len(chunk) > left:
                                chunk = chunk[:left]
                            f.write(chunk)
                            with self._lock:
                                self._done += len(chunk)
                            # 记录该块进度，供中断后续传
                            state.chunks[index]["done"] = f.tell() - int(
                                state.chunks[index]["start"])
                            if f.tell() > end:
                                break
            except Exception:
                if self._cancel:
                    return
                raise
            finally:
                if r in self._responses:
                    self._responses.remove(r)

        ok = False
        try:
            with ThreadPoolExecutor(max_workers=max(1, len(jobs))) as ex:
                futures = [ex.submit(worker, i, s, e) for i, s, e in jobs]
                try:
                    last_save = 0.0
                    while any(not f.done() for f in futures):
                        if self._cancel:
                            self.cancel()  # 断开所有连接，让各块尽快退出
                            break
                        with self._lock:
                            done = self._done
                        self.progress.emit(done, total)
                        # 每秒落盘一次进度：中途崩溃/断网也不会白下太多
                        now = time.time()
                        if now - last_save >= 1.0:
                            state.save(self.dest)
                            last_save = now
                        time.sleep(0.15)
                    for f in futures:
                        f.result()
                except RangeUnsupported:
                    raise
                except Exception:
                    if self._cancel:
                        self._emit_cancelled()
                        return False
                    raise  # 网络类错误：保留进度，交给上层切通道续传

            if self._cancel:
                self._emit_cancelled()
                return False
            # 完整性校验：任一块没写满就当作失败（否则会拿到半个文件）
            missing = [
                c for c in chunks
                if int(c.get("done", 0)) != int(c["end"]) - int(c["start"]) + 1
            ]
            if missing:
                self.log.emit("warn", f"{len(missing)} 个分块未完整下载。")
                return False
            self.progress.emit(total, total)
            ok = True
            return True
        finally:
            if not ok:
                # 中断/取消都保留进度，下次继续
                state.save(self.dest)

    def _download_plain(self, url: str, tmp: Path, meta: Optional[FileMeta],
                        state: Optional[ResumeState]) -> bool:
        """单线程流式下载（分块不可用时的兜底路径），同样支持断点续传。

        先尝试续传；若服务端没按要求只给剩余部分（有的镜像返回 206 却回全量），
        则丢弃进度完整重下一次。
        """
        done = 0
        if state is not None and state.mode == "plain" and tmp.exists():
            done = min(state.downloaded(), tmp.stat().st_size)
        if done > 0 and _host(url) in _BAD_RESUME:
            # 这个地址上次「假续传」（返回 206 却给全量），别再浪费一次下载
            self.log.emit("warn", "该地址此前不支持断点续传，直接完整下载。")
            done = 0
        if self._plain_once(url, tmp, meta, state if done > 0 else None, done):
            return True
        if self._cancel:
            return False
        if done > 0:
            _BAD_RESUME.add(_host(url))
        self.log.emit("warn", "续传数据长度异常，改为完整重新下载。")
        ResumeState.discard(self.dest)
        return self._plain_once(url, tmp, meta, None, 0)

    def _plain_once(self, url: str, tmp: Path, meta: Optional[FileMeta],
                    state: Optional[ResumeState], done: int) -> bool:
        """单线程下载一次：done>0 时带 Range 续传。成功且大小正确返回 True。"""
        headers = dict(self.headers or {})
        # 不接受压缩：解压后的长度与 Content-Length 对不上会破坏续传偏移
        headers.setdefault("Accept-Encoding", "identity")
        if done > 0:
            headers["Range"] = f"bytes={done}-"
        # 走统一入口：MITM 代理/加速器导致证书校验失败时会自动降级重试
        r = http_get(
            url, timeout=30, headers=headers or None, stream=True,
            allow_redirects=True,
            on_note=lambda m: self.log.emit("warn", m),
        )
        self._responses.append(r)
        ok = False
        new_state: Optional[ResumeState] = None
        try:
            with r:
                # 响应阶段也可能收到取消（下载循环开始前只有这里能响应）
                if self._cancel:
                    self._emit_cancelled()
                    return False
                if done > 0 and r.status_code != 206:
                    return False  # 服务端不接受续传，交给外层完整重下
                remaining = int(r.headers.get("Content-Length", 0) or 0)
                expected_total = meta.total if meta is not None else 0
                # 只写到 expected_total 为止：有的镜像返回 206 却回全量，
                # 不截断就会把文件写大
                limit = (expected_total - done) if (
                    done > 0 and expected_total > done) else remaining
                total = done + limit
                if state is None:
                    state = ResumeState(url=url, total=total, mode="plain", parts=1)
                    if meta is not None:
                        state.etag = meta.etag
                        state.last_modified = meta.last_modified
                    state.chunks = [{"start": 0, "end": max(total - 1, 0), "done": done}]
                new_state = state
                downloaded = done
                last_save = 0.0
                with open(tmp, "ab" if done > 0 else "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if self._cancel:
                            f.close()
                            self._emit_cancelled()
                            return False
                        if not chunk:
                            continue
                        if limit and downloaded + len(chunk) > done + limit:
                            chunk = chunk[:done + limit - downloaded]
                        f.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total)
                        now = time.time()
                        if now - last_save >= 1.0:
                            state.chunks[0]["done"] = downloaded
                            state.save(self.dest)
                            last_save = now
                        if limit and downloaded >= done + limit:
                            break
                # 大小不对（续传数据不干净）→ 让外层完整重下
                if expected_total and tmp.stat().st_size != expected_total:
                    return False
                tmp.replace(self.dest)
            ok = True
            self._emit_ok()
            return True
        finally:
            if r in self._responses:
                self._responses.remove(r)
            if not ok and new_state is not None:
                # 中断/取消：保存已下载字节数，下次从这里继续
                new_state.save(self.dest)

    def _emit_ok(self) -> None:
        # 已完成：清掉续传状态（.part 已被 rename 成目标文件）
        ResumeState.clear(self.dest)
        self.log.emit(
            "ok", f"下载完成：{self.dest} ({human_size(self.dest.stat().st_size)})")
        self.finished_ok.emit(str(self.dest))

    def run(self) -> None:  # noqa: D401
        try:
            channels = self._channels()
            if self._cancel:
                self._emit_cancelled()
                return
            last_exc: Optional[Exception] = None
            for idx, (label, url) in enumerate(channels):
                try:
                    self._download(url, label)
                    return
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if idx + 1 < len(channels):
                        self.log.emit("warn", f"通道「{label}」下载失败，切换下一个：{exc}")
            assert last_exc is not None
            raise last_exc
        except Exception as exc:  # pragma: no cover
            self.log.emit("error", f"下载失败：{exc}")
            self.finished_fail.emit(str(exc))


class MirrorProbeWorker(QThread):
    """镜像测速线程（供设置界面使用），完成后给出各通道速度。"""

    done = Signal(object)  # [(id, 名称, KB/s)]，按速度降序，失败为 -1

    def __init__(self, url: Optional[str] = None,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.url = url

    def run(self) -> None:  # noqa: D401
        self.done.emit(MIRRORS.probe(self.url or PROBE_URL))


class UpdateCheckWorker(QThread):
    """检查软件更新的后台线程（供设置界面「检查更新」使用）。"""

    done = Signal(object)   # UpdateInfo
    failed = Signal(str)    # 错误信息
    note = Signal(str)      # 过程提示（如证书降级）

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

    def run(self) -> None:  # noqa: D401
        try:
            self.done.emit(fetch_latest(on_note=self.note.emit))
        except Exception as exc:  # pragma: no cover
            self.failed.emit(str(exc))


class CommandWorker(QThread):
    """在后台执行外部命令（如 npm 便携安装），并把输出实时转发到日志。"""

    log = Signal(str, str)  # (level, message)
    finished_ok = Signal(str)
    finished_fail = Signal(str)

    def __init__(self, cmd: List[str], cwd: Optional[Path] = None,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.cmd = cmd
        self.cwd = str(cwd) if cwd else None
        self._proc: Optional[subprocess.Popen] = None
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True
        if self._proc is not None and self._proc.poll() is None:
            try:
                if CURRENT_OS == "Windows":
                    self._proc.terminate()
                else:
                    import signal
                    os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except Exception:
                pass

    def run(self) -> None:  # noqa: D401
        try:
            self.log.emit("info", f"执行：{' '.join(self.cmd)}（目录：{self.cwd or os.getcwd()}）")
            kwargs = dict(
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                encoding="utf-8",
                errors="replace",
            )
            if CURRENT_OS != "Windows":
                kwargs["start_new_session"] = True
            self._proc = subprocess.Popen(self.cmd, **kwargs)
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                text = line.rstrip()
                if text:
                    self.log.emit("info", text[:500])
            code = self._proc.wait()
            if self._cancel:
                self.finished_fail.emit("用户取消")
                return
            if code != 0:
                self.finished_fail.emit(f"命令返回非零退出码：{code}")
                return
            self.finished_ok.emit("")
        except Exception as exc:  # pragma: no cover
            self.log.emit("error", f"命令执行失败：{exc}")
            self.finished_fail.emit(str(exc))
