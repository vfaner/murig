# -*- coding: utf-8 -*-
"""GitHub 版本抓取自检：验证 API 限流/拦截时的回退链路是否可用。

用法：
    python tools/check_github.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from murig.catalog.fetch import (  # noqa: E402
    _github_releases, _github_tags, _github_asset_names,
    fetch_git_versions, fetch_es_versions, fetch_ollama_versions,
    fetch_ccswitch_versions, fetch_oceanbase_versions,
)


def main() -> int:
    print("=== GitHub 通道自检 ===")
    for fn in (fetch_git_versions, fetch_es_versions, fetch_ollama_versions,
               fetch_ccswitch_versions, fetch_oceanbase_versions):
        try:
            vs = fn()
            print(f"[ok]   {fn.__name__:26s} {len(vs)} 个版本，例：{[v.version for v in vs[:3]]}")
        except Exception as e:
            print(f"[fail] {fn.__name__:26s} {e}")

    print("\n=== 回退通道（不走 API） ===")
    try:
        rels = _github_releases("git-for-windows", "git", 20)
        print(f"[ok]   releases.atom 回退：{len(rels)} 条，tag 例：{[r['tag_name'] for r in rels[:3]]}")
    except Exception as e:
        print(f"[fail] releases.atom 回退：{e}")
    try:
        tags = _github_tags("elastic", "elasticsearch", 60)
        print(f"[ok]   tags 回退：{len(tags)} 条")
    except Exception as e:
        print(f"[fail] tags 回退：{e}")
    assets = _github_asset_names("ollama", "ollama", "v0.12.0")
    print(f"[info] expanded_assets 附件名：{assets[:3] if assets else '（空，可能被拦截）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
