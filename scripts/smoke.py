#!/usr/bin/env python3
"""对运行中的 API 做冒烟检查：健康、前端、可行配片、不可行证据、参数校验。

通过环境变量 API_BASE 指定服务地址（默认 http://127.0.0.1:8000）。
全部通过退出码为 0，否则为 1。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
failures = []


def check(name, cond, extra=""):
    if cond:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(name)


def request(method, path, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body}


def wait_ready(attempts=60):
    for _ in range(attempts):
        try:
            status, body = request("GET", "/health")
            if status == 200 and body and body.get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


FEASIBLE = {
    "damages": [
        {"id": "D1", "width": 8, "height": 10, "phaseMin": 0, "phaseMax": 5},
        {"id": "D2", "width": 8, "height": 10, "phaseMin": 0, "phaseMax": 5},
        {"id": "D3", "width": 8, "height": 10, "phaseMin": 0, "phaseMax": 5},
    ],
    "scraps": [
        {"id": "S1", "region": {"x": 0, "y": 0, "width": 40, "height": 20}, "period": 6, "origin": 0, "maxUses": 3},
        {"id": "S2", "region": {"x": 0, "y": 0, "width": 30, "height": 20}, "period": 6, "origin": 0, "maxUses": 1},
        {"id": "S3", "region": {"x": 5, "y": 0, "width": 30, "height": 20}, "period": 6, "origin": 2, "maxUses": 1},
        {"id": "S4", "region": {"x": 0, "y": 0, "width": 25, "height": 12}, "period": 6, "origin": 0, "maxUses": 1},
    ],
}


def check_plan_consistency(payload, data):
    """独立复算返回方案，验证其满足全部业务约束。"""
    damages = payload["damages"]
    scraps = payload["scraps"]
    plan = data["plan"]
    check("plan 长度与破损数一致", len(plan) == len(damages))
    per_scrap = {}
    ok = True
    for i, p in enumerate(plan):
        d = damages[p["damageIndex"]]
        s = scraps[p["scrapIndex"]]
        if not (s["region"]["x"] <= p["start"] and p["start"] + d["width"] <= s["region"]["x"] + s["region"]["width"]):
            ok = False
        if d["height"] > s["region"]["height"]:
            ok = False
        if p["leftPhase"] != (s["origin"] + p["start"]) % s["period"]:
            ok = False
        if p["rightPhase"] != (s["origin"] + p["start"] + d["width"]) % s["period"]:
            ok = False
        if not (d["phaseMin"] <= p["leftPhase"] <= d["phaseMax"]):
            ok = False
        per_scrap.setdefault(p["scrapIndex"], []).append((p["start"], p["start"] + d["width"]))
    check("裁片不越界且相位计算正确", ok)
    ok = True
    for si, ivs in per_scrap.items():
        if len(ivs) > scraps[si]["maxUses"]:
            ok = False
        ivs.sort()
        for (a0, a1), (b0, b1) in zip(ivs, ivs[1:]):
            if a1 > b0:
                ok = False
    check("同一边料裁片不重叠且不超可用次数", ok)
    ok = all(a["rightPhase"] == b["leftPhase"] for a, b in zip(plan, plan[1:]))
    check("相邻破损相位连续", ok)
    obj = data["objectives"]
    check("目标统计一致", obj["scrapsUsed"] == len(per_scrap)
          and obj["wasteArea"] == obj["usedRegionArea"] - obj["piecesArea"])


def main():
    print(f"等待服务就绪: {BASE}")
    if not wait_ready():
        print("  FAIL 服务未在限定时间内就绪")
        sys.exit(1)

    status, body = request("GET", "/health")
    check("GET /health", status == 200 and body.get("status") == "ok")

    req = urllib.request.Request(BASE + "/", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode()
            check("GET / 返回前端页面", resp.status == 200 and "古籍" in html)
    except Exception as exc:
        check("GET / 返回前端页面", False, str(exc))

    status, data = request("POST", "/api/solve", FEASIBLE)
    check("POST /api/solve 可行场景返回 200 且 feasible",
          status == 200 and data.get("status") == "feasible")
    if status == 200 and data.get("status") == "feasible":
        check_plan_consistency(FEASIBLE, data)

    infeasible = json.loads(json.dumps(FEASIBLE))
    for d in infeasible["damages"]:
        d["width"] = 500
    status, data = request("POST", "/api/solve", infeasible)
    check("POST /api/solve 不可行场景返回首条约束证据",
          status == 200 and data.get("status") == "infeasible"
          and data.get("evidence", {}).get("constraint") == "piece_exceeds_region"
          and bool(data.get("evidence", {}).get("message")))

    invalid = json.loads(json.dumps(FEASIBLE))
    invalid["damages"] = invalid["damages"][:2]
    status, _ = request("POST", "/api/solve", invalid)
    check("POST /api/solve 非法输入返回 422", status == 422)

    if failures:
        print(f"SMOKE FAILED: {len(failures)} 项未通过")
        sys.exit(1)
    print("SMOKE OK")


if __name__ == "__main__":
    main()
