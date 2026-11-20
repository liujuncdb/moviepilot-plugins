#!/usr/bin/env python3
"""发布前检查：索引版本、目录命名、图标与 Python 语法。"""
import json
import re
import sys
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEXES = [
    ("package.v3.json", ROOT / "plugins.v3"),
    ("package.json", ROOT / "plugins"),
]


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    sys.exit(1)


def check_plugin(index_name: str, source_root: Path, plugin_id: str, entry: dict) -> None:
    plugin_dir = source_root / plugin_id.lower()
    if not plugin_dir.exists():
        fail(f"{index_name}: 缺少插件目录 {plugin_dir.relative_to(ROOT)}")

    source = (plugin_dir / "__init__.py").read_text(encoding="utf-8")
    class_match = re.search(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", source, re.M)
    if not class_match:
        fail(f"{index_name}/{plugin_id}: __init__.py 未找到插件主类")
    class_name = class_match.group(1)
    if class_name.lower() != plugin_dir.name:
        fail(f"{plugin_id}: 目录名 {plugin_dir.name} 与主类 {class_name} 的小写不一致")

    version_match = re.search(r'^\s*plugin_version\s*=\s*"([^"]+)"', source, re.M)
    if not version_match:
        fail(f"{plugin_id}: __init__.py 缺少 plugin_version")
    plugin_version = version_match.group(1)
    if entry.get("version") != plugin_version:
        fail(f"{index_name}/{plugin_id}: version={entry.get('version')} 与 plugin_version={plugin_version} 不一致")

    history = entry.get("history") or {}
    if not history:
        fail(f"{index_name}/{plugin_id}: 缺少 history")
    latest = next(iter(history))
    if latest not in (f"v{plugin_version}", plugin_version):
        fail(f"{index_name}/{plugin_id}: history 顶部为 {latest}，应为 v{plugin_version} 或 {plugin_version}")

    icon = str(entry.get("icon") or "")
    if icon and not icon.startswith(("http://", "https://")):
        candidates = [ROOT / "icons" / icon, plugin_dir / icon]
        if not any(p.exists() for p in candidates):
            fail(f"{index_name}/{plugin_id}: 图标不存在 {icon}")

    if "__GITHUB_OWNER__" in source:
        fail(f"{plugin_id}: 源码仍包含仓库所有者占位符")

    for py_file in plugin_dir.rglob("*.py"):
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as exc:
            fail(f"语法检查失败：{py_file.relative_to(ROOT)}\n{exc}")
    print(f"[OK] {index_name}: {plugin_id} {plugin_version} -> {plugin_dir.relative_to(ROOT)}")


def main() -> None:
    for index_name, source_root in INDEXES:
        index_path = ROOT / index_name
        if not index_path.exists():
            fail(f"缺少 {index_name}")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for plugin_id, entry in index.items():
            check_plugin(index_name, source_root, plugin_id, entry)
    print("[OK] 全部索引、版本、图标与语法检查通过")


if __name__ == "__main__":
    main()
