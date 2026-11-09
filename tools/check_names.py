# -*- coding: utf-8 -*-
"""静态检查：找出各模块中引用了却没有绑定的名字（含 star import 解析）。

用于拆分重构后快速补齐 import，比反复跑 GUI 冒烟更快。
用法： python tools/check_names.py
"""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "murig"
BUILTINS = set(dir(builtins))


def top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def bound_names(tree: ast.AST, module_dir: Path) -> set[str]:
    bound: set[str] = set()
    stars: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    mod = ("." * (node.level or 0)) + (node.module or "")
                    stars.append(mod)
                else:
                    bound.add(a.asname or a.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
            # 装饰器、默认值、注解里用到的名字由 walk 覆盖
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, ast.comprehension):
            pass
    # 解析相对 star import：把被导入模块的顶层名字并入
    for mod in stars:
        rel = mod.lstrip(".")
        target = module_dir / (rel.replace(".", "/") + ".py")
        if not target.exists():
            target = module_dir / rel / "__init__.py"
        if target.exists():
            bound |= top_level_names(target)
    return bound


def main() -> None:
    for path in sorted(PKG.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bound = bound_names(tree, path.parent)
        used: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used.setdefault(node.id, node.lineno)
        missing = {k: v for k, v in used.items() if k not in bound and k not in BUILTINS}
        if missing:
            rel = path.relative_to(ROOT).as_posix()
            items = ", ".join(f"{k}@{v}" for k, v in sorted(missing.items(), key=lambda x: x[1]))
            print(f"{rel}\n    {items}")


if __name__ == "__main__":
    main()
