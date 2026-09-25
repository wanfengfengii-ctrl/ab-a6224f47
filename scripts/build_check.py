#!/usr/bin/env python3
"""构建检查：字节编译全部 Python 源码、导入应用模块、校验前端资产完整性。"""
import compileall
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ok = True

print("  编译 Python 源码 ...")
for sub in ("app", "scripts", "tests"):
    if not compileall.compile_dir(ROOT / sub, quiet=1, force=True):
        ok = False
        print(f"  编译失败: {sub}")

print("  导入应用模块 ...")
try:
    sys.path.insert(0, str(ROOT))
    import app.main  # noqa: F401
except Exception as exc:  # pragma: no cover - 仅在构建失败时触发
    ok = False
    print(f"  导入失败: {exc}")

print("  校验前端资产 ...")
static = ROOT / "app" / "static"
index_path = static / "index.html"
for name in ("index.html", "app.js", "style.css"):
    p = static / name
    if not p.is_file() or p.stat().st_size == 0:
        ok = False
        print(f"  缺少或为空: {name}")
if index_path.is_file():
    index = index_path.read_text(encoding="utf-8")
    for ref in ("/static/app.js", "/static/style.css"):
        if ref not in index:
            ok = False
            print(f"  index.html 未引用 {ref}")

if not ok:
    print("BUILD CHECK FAILED")
    sys.exit(1)
print("  构建检查通过")
