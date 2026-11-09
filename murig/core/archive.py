# -*- coding: utf-8 -*-
"""归档解包：zip / tar / tar.gz / tar.xz / RPM(cpio)。"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Dict

from .utils import ensure_dir


# ---------------------------------------------------------------------------
# 归档解压
# ---------------------------------------------------------------------------
def extract_archive(archive: Path, extract_to: Path) -> Path:
    """解压归档，返回解压后（通常包含一个根目录）的根路径。"""
    ensure_dir(extract_to)
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(extract_to)
    elif name.endswith(".tar.gz") or name.endswith(".tgz"):
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(extract_to)
    elif name.endswith(".tar.xz"):
        with tarfile.open(archive, "r:xz") as tf:
            tf.extractall(extract_to)
    elif name.endswith(".tar"):
        # 后缀是 .tar 但可能实为 gzip 压缩（KingbaseES 便携包即如此）；
        # r:* 按魔术字节自动识别压缩格式，真未压缩 tar 也兼容
        with tarfile.open(archive, "r:*") as tf:
            tf.extractall(extract_to)
    else:
        raise RuntimeError(f"未知的归档类型：{archive.name}")

    entries = [p for p in extract_to.iterdir() if p.is_dir()]
    if len(entries) == 1:
        return entries[0]
    return extract_to


def _rpm_header_info(data: bytes):
    """解析 RPM 的 lead + signature header + immutable header。

    返回 (payload 起始偏移, payload 压缩器, 格式)。仅解析 header 索引区。
    索引项为 16 字节：tag / type / offset / count。
    """
    def one_header(off: int):
        if data[off:off + 3] != b"\x8e\xad\xe8":
            raise RuntimeError("不是有效的 RPM 包（header magic 不匹配）")
        count = int.from_bytes(data[off + 8:off + 12], "big")
        dbytes = int.from_bytes(data[off + 12:off + 16], "big")
        tags: Dict[int, tuple] = {}
        idx = off + 16
        for _ in range(count):
            tag, typ, noff, cnt = (
                int.from_bytes(data[idx:idx + 4], "big"),
                int.from_bytes(data[idx + 4:idx + 8], "big"),
                int.from_bytes(data[idx + 8:idx + 12], "big"),
                int.from_bytes(data[idx + 12:idx + 16], "big"),
            )
            tags[tag] = (typ, noff, cnt)
            idx += 16
        return tags, idx, dbytes

    # lead 固定 96 字节
    _sig_tags, sig_store, sig_db = one_header(96)
    sig_end = sig_store + ((sig_db + 7) // 8 * 8)
    hdr_tags, hdr_store, hdr_db = one_header(sig_end)

    def header_string(tag: int) -> str:
        _, off, _ = hdr_tags[tag]
        end = data.index(b"\x00", hdr_store + off)
        return data[hdr_store + off:end].decode()

    # immutable store 后直接衔接 payload（尾部不补齐；8 字节对齐只用于两个 header 之间）
    payload_off = hdr_store + hdr_db
    return payload_off, header_string(1125), header_string(1124)


def extract_rpm(rpm: Path, extract_to: Path) -> Path:
    """把 RPM（cpio + xz/gzip/zstd）解包到目录，返回 extract_to。

    不依赖系统 rpm2cpio；xz/gzip 走标准库，zstd 需要系统 zstd 命令。
    """
    import lzma
    import gzip

    ensure_dir(extract_to)
    with open(rpm, "rb") as f:
        head = f.read(512 * 1024)
        payload_off, compressor, payload_fmt = _rpm_header_info(head)
        f.seek(payload_off)

        cpio_tmp = extract_to.parent / f".{rpm.stem}.cpio"
        with open(cpio_tmp, "wb") as out:
            if compressor in ("xz", "lzma"):
                dec = lzma.LZMADecompressor()
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(dec.decompress(chunk))
            elif compressor == "gzip":
                dec = gzip.GzipFile(fileobj=f)
                shutil.copyfileobj(dec, out)
            elif compressor == "zstd":
                zstd = shutil.which("zstd")
                if not zstd:
                    raise RuntimeError("该 RPM 使用 zstd 压缩，请先安装 zstd（brew install zstd / apt install zstd）")
                proc = subprocess.Popen(
                    [zstd, "-dc", "-"], stdin=subprocess.PIPE, stdout=out,
                )
                try:
                    shutil.copyfileobj(f, proc.stdin)
                finally:
                    if proc.stdin:
                        proc.stdin.close()
                if proc.wait() != 0:
                    raise RuntimeError("zstd 解压失败")
            else:
                raise RuntimeError(f"暂不支持的 RPM 压缩格式：{compressor}（payload={payload_fmt}）")

    _extract_cpio_newc(cpio_tmp, extract_to)
    cpio_tmp.unlink(missing_ok=True)
    return extract_to


def _extract_cpio_newc(cpio_file: Path, dest: Path) -> None:
    """流式解析 cpio newc（magic 070701/070702）归档并提取文件。"""
    with open(cpio_file, "rb") as data:
        while True:
            h = data.read(110)
            if len(h) < 110 or h[:6] not in (b"070701", b"070702"):
                break
            filesize = int(h[54:62], 16)
            namesize = int(h[94:102], 16)
            mode = int(h[14:22], 16)
            raw_name = data.read(namesize)
            name = raw_name[:-1].decode("utf-8", "replace")
            # 头部(110) + 名称整体按 4 字节对齐
            data.seek((-(110 + namesize)) % 4, 1)

            if name == "TRAILER!!!":
                break
            # 规范掉 ./ 与 / 前缀（RPM 内名称常见 "./usr/..."）
            rel = name
            while rel.startswith("./"):
                rel = rel[2:]
            rel = rel.lstrip("/")
            ftype = mode & 0o170000
            target = dest / rel if rel else None

            if target is not None and ftype == 0o040000:  # 目录
                target.mkdir(parents=True, exist_ok=True)
                data.seek((-filesize) % 4, 1)
            elif target is not None and ftype == 0o120000:  # 软链接
                link = data.read(filesize).decode("utf-8", "replace")
                data.seek((-filesize) % 4, 1)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink() or target.exists():
                    target.unlink()
                target.symlink_to(link)
            elif target is not None and ftype == 0o100000:  # 普通文件
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "wb") as out:
                    remaining = filesize
                    while remaining > 0:
                        chunk = data.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        out.write(chunk)
                        remaining -= len(chunk)
                try:
                    target.chmod(mode & 0o777)
                except OSError:
                    pass
                data.seek((-filesize) % 4, 1)
            else:
                # 其它类型（设备/fifo 等）跳过数据体
                data.seek(filesize + ((-filesize) % 4), 1)
