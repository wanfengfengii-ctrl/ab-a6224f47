#!/usr/bin/env bash
# 一次性验证入口：代码测试 -> 构建检查 -> API 冒烟。
# 任一阶段失败即以非零退出码结束（set -e），供 docker compose 的 verify 服务使用。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export API_BASE="${API_BASE:-http://127.0.0.1:8000}"

echo "== [1/3] 代码测试（pytest）=="
python -m pytest tests -q

echo "== [2/3] 构建检查 =="
python scripts/build_check.py

echo "== [3/3] API 冒烟（${API_BASE}）=="
python scripts/smoke.py

echo "VERIFY OK"
