# -*- coding: utf-8 -*-
"""统一的网络请求入口：自动重试 + 证书降级。

企业代理 / 加速器 / 上网行为管理普遍会做 TLS 中间人（MITM），此时 Python 自带的
证书库校验会直接失败（CERTIFICATE_VERIFY_FAILED），表现为"下载失败"而不是"没网"。
这里按三级策略处理，并让下载与版本抓取共用同一套逻辑：

    1) 正常证书校验
    2) 校验失败 -> 若环境装了 truststore，改用操作系统证书库重试
    3) 仍失败 -> 关闭校验重试（最后兜底，会打印告警提示）

4xx（401/403/404/429）不会因重试而改变，直接抛出，避免浪费本就紧张的 API 配额。
"""

from __future__ import annotations

import time
import warnings
from typing import Callable, Dict, Optional

import requests

__all__ = ["get"]


def _disable_insecure_warnings() -> None:
    try:  # pragma: no cover
        import urllib3
        warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass


def _try_system_certs() -> bool:
    """若装了 truststore，则让后续请求使用操作系统证书库（比关闭校验安全）。"""
    try:  # pragma: no cover - 依赖可选
        import truststore  # type: ignore
        truststore.inject_into_ssl()
        return True
    except Exception:
        return False


def get(url: str, *, timeout: int = 10, headers: Optional[Dict[str, str]] = None,
        stream: bool = False, on_note: Optional[Callable[[str], None]] = None,
        **kwargs) -> requests.Response:
    """带重试与证书降级的 GET。

    on_note：可选的提示回调，用于把"证书降级"等事件显示到界面日志。
    """
    headers = headers or {"User-Agent": "MuRig"}
    last_exc: Optional[Exception] = None
    mode = 0  # 0=正常校验 1=系统证书库 2=关闭校验

    for attempt in range(4):
        if mode == 1 and not _try_system_certs():
            mode = 2  # 没有 truststore 就直接跳到关闭校验
        if mode == 2:
            _disable_insecure_warnings()
        resp = None
        try:
            resp = requests.get(url, timeout=timeout, headers=headers, stream=stream,
                                verify=(mode != 2), **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as e:
            if resp is not None:
                resp.close()
            code = getattr(getattr(e, "response", None), "status_code", 0)
            if 400 <= code < 500:
                raise  # 4xx 重试无意义
            last_exc = e
        except requests.exceptions.SSLError as e:
            if resp is not None:
                resp.close()
            last_exc = e
            if mode == 0:
                mode = 1
                if on_note:
                    on_note("证书校验失败，正在改用系统证书库重试…")
            else:
                mode = 2
                if on_note:
                    on_note("证书校验仍失败，已跳过校验重试（多见于加速器 / 企业代理）")
        except Exception as e:
            if resp is not None:
                resp.close()
            last_exc = e
        if attempt < 3:
            time.sleep(1 << min(attempt, 2))  # 1s, 2s, 2s

    assert last_exc is not None
    raise last_exc
