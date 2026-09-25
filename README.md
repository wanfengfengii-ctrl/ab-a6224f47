# 古籍补纸配片台

古籍修复室的补纸配片工具：修复师在网页录入按阅读方向排列的 3–5 处破损与 4–8 张边料，
服务端为每处破损恰选一张边料及整数裁切起点，使相邻破损的水印线相位保持连续，
并在多组可行方案中按既定优先级选出最优者；无法配片时返回首条约束证据。

## 领域规则

- 边料 `s` 上位置 `pos` 处的水印相位为 `(origin_s + pos) mod period_s`。
- 破损 `d` 的裁片宽 `w_d`、高 `h_d`，整数裁切起点 `x` 满足
  `s.x ≤ x`、`x + w_d ≤ s.x + s.width`、`h_d ≤ s.height`（不得越界）。
- 裁片左缘相位必须落在破损要求的 `[phaseMin, phaseMax]` 内。
- 相邻破损（按输入顺序）：前一处裁片**右缘相位** = 后一处裁片**左缘相位**（各自按周期折算）。
- 同一边料上的裁片区间 `[x, x + w)` 不得重叠；每张边料至多承载 `maxUses` 个裁片。

## 目标优先级（存在多个可行方案时依次比较）

1. **使用边料张数最少**（一张边料被裁多片仍计 1 张）；
2. **裁切废料总面积最小**（= 被使用边料的可裁区域总面积 − 全部裁片面积；
   裁片总面积固定，等价于最小化被使用边料的区域面积之和）；
3. **按破损输入顺序展开的 `(边料序号, 裁切起点)` 序列字典序最小**（序号按边料输入顺序从 0 计）。

## 不可行时的首条约束证据

按以下顺序检查并返回第一条失败的约束（`evidence.constraint`）：

| constraint | 含义 |
| --- | --- |
| `piece_exceeds_region` | 某处破损所需裁片超出所有边料的可裁区域 |
| `phase_range_unreachable` | 某处破损要求的相位范围在任何边料上都不可达 |
| `phase_continuity` | 相邻两处破损之间水印相位无法衔接（忽略次数/重叠仍不可行） |
| `scrap_capacity_or_overlap` | 边料可用次数 / 同料重叠导致的资源冲突 |

响应中包含 `damageIndex`（0 起）、人类可读 `message` 与结构化 `details`。

## 项目结构

```
app/
  main.py        FastAPI 应用：/health、/api/solve、前端静态资源
  schemas.py     请求校验（3–5 处破损、4–8 张边料等）
  solver.py      核心求解器（分支限界 DFS + 三级目标 + 分层证据）
  static/        前端单页（index.html / app.js / style.css）
tests/           pytest 单元与 API 测试（含暴力枚举交叉验证）
scripts/
  verify.sh      一次性验证：代码测试 -> 构建检查 -> API 冒烟
  build_check.py 构建检查（字节编译 + 导入 + 前端资产）
  smoke.py       API 冒烟（健康/可行/不可行/校验，独立复算方案）
Dockerfile
docker-compose.yml
```

## 快速开始（Docker Compose）

```bash
# 启动应用（宿主机端口默认 8080，可用 HOST_PORT 覆盖）
HOST_PORT=9000 docker compose up --build app

# 一键验证：代码测试 + 构建检查 + API 冒烟，以 verify 的退出码报告结果
docker compose up --build --exit-code-from verify verify
```

启动后访问 `http://localhost:8080`（或自定义端口）使用前端；
交互式 API 文档位于 `http://localhost:8080/docs`。

## 本地开发

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 测试与验证（需服务已启动用于冒烟）
pytest -q
API_BASE=http://127.0.0.1:8000 bash scripts/verify.sh
```

## API

### `GET /health`

健康检查，返回 `{"status": "ok"}`。

### `POST /api/solve`

请求体：

```json
{
  "damages": [
    {"id": "D1", "width": 8, "height": 10, "phaseMin": 0, "phaseMax": 5}
  ],
  "scraps": [
    {"id": "S1", "region": {"x": 0, "y": 0, "width": 40, "height": 20},
     "period": 6, "origin": 0, "maxUses": 3}
  ]
}
```

- `damages`：3–5 处，按阅读方向排列；`phaseMin ≤ phaseMax`。
- `scraps`：4–8 张；`region` 为可裁区域；`period ≥ 1`；`maxUses ≥ 1`；id 各自唯一。
- 校验失败返回 422。

可行响应（200）：

```json
{
  "status": "feasible",
  "objectives": {"scrapsUsed": 1, "usedRegionArea": 800, "piecesArea": 240, "wasteArea": 560},
  "plan": [
    {"damageIndex": 0, "damageId": "D1", "scrapIndex": 0, "scrapId": "S1",
     "start": 0, "y": 0, "width": 8, "height": 10, "leftPhase": 0, "rightPhase": 2}
  ]
}
```

不可行响应（200）：

```json
{
  "status": "infeasible",
  "evidence": {
    "constraint": "piece_exceeds_region",
    "damageIndex": 0,
    "message": "破损 D1（第 1 处）所需裁片 500×10 超出所有边料的可裁区域（现有最大可裁区域 40×20）",
    "details": {"damageId": "D1", "required": {"width": 500, "height": 10}, "maxRegion": {"width": 40, "height": 20}}
  }
}
```

示例：

```bash
curl -s -X POST http://localhost:8080/api/solve \
  -H 'Content-Type: application/json' \
  -d '{"damages":[{"id":"D1","width":8,"height":10,"phaseMin":0,"phaseMax":5},
                    {"id":"D2","width":8,"height":10,"phaseMin":0,"phaseMax":5},
                    {"id":"D3","width":8,"height":10,"phaseMin":0,"phaseMax":5}],
       "scraps":[{"id":"S1","region":{"x":0,"y":0,"width":40,"height":20},"period":6,"origin":0,"maxUses":3},
                 {"id":"S2","region":{"x":0,"y":0,"width":30,"height":20},"period":6,"origin":0,"maxUses":1},
                 {"id":"S3","region":{"x":5,"y":0,"width":30,"height":20},"period":6,"origin":2,"maxUses":1},
                 {"id":"S4","region":{"x":0,"y":0,"width":25,"height":12},"period":6,"origin":0,"maxUses":1}]}'
```

## 前端使用

1. 在“破损”表格中按阅读方向维护 3–5 行（宽、高、相位上下限）。
2. 在“边料”表格中维护 4–8 行（可裁区域、纹样周期、相位原点、可用次数）。
3. 可随时“保存草稿”（存于浏览器 localStorage，刷新后自动恢复）、“载入示例”或“清除草稿”。
4. 点击“发起配片”：可行时展示每处破损的边料、裁切起点与两侧相位及目标统计；
   不可行时展示首条约束证据；输入不合法时列出全部校验问题。
