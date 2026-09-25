"""API 层测试：健康检查、配片接口、校验错误。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def feasible_payload():
    return {
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


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_index_served():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "古籍" in resp.text


def test_static_assets_served():
    for path in ("/static/app.js", "/static/style.css"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert len(resp.content) > 0


def test_solve_feasible():
    resp = client.post("/api/solve", json=feasible_payload())
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "feasible"
    assert data["objectives"]["scrapsUsed"] == 1
    assert data["objectives"]["wasteArea"] == 800 - 240
    plan = data["plan"]
    assert len(plan) == 3
    assert [p["start"] for p in plan] == [0, 8, 16]
    assert [p["scrapId"] for p in plan] == ["S1", "S1", "S1"]
    assert [p["leftPhase"] for p in plan] == [0, 2, 4]
    assert [p["rightPhase"] for p in plan] == [2, 4, 0]
    for a, b in zip(plan, plan[1:]):
        assert a["rightPhase"] == b["leftPhase"]


def test_solve_infeasible_returns_first_evidence():
    payload = feasible_payload()
    for d in payload["damages"]:
        d["width"] = 500
    resp = client.post("/api/solve", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "infeasible"
    ev = data["evidence"]
    assert ev["constraint"] == "piece_exceeds_region"
    assert ev["damageIndex"] == 0
    assert ev["message"]
    assert ev["details"]["damageId"] == "D1"


def test_validation_too_few_damages():
    payload = feasible_payload()
    payload["damages"] = payload["damages"][:2]
    resp = client.post("/api/solve", json=payload)
    assert resp.status_code == 422


def test_validation_too_many_scraps():
    payload = feasible_payload()
    extra = {"region": {"x": 0, "y": 0, "width": 10, "height": 10}, "period": 6, "origin": 0, "maxUses": 1}
    payload["scraps"] = payload["scraps"] + [
        dict(extra, id=f"X{i}") for i in range(6)
    ]
    resp = client.post("/api/solve", json=payload)
    assert resp.status_code == 422


def test_validation_phase_range():
    payload = feasible_payload()
    payload["damages"][0]["phaseMin"] = 4
    payload["damages"][0]["phaseMax"] = 2
    resp = client.post("/api/solve", json=payload)
    assert resp.status_code == 422


def test_validation_duplicate_ids():
    payload = feasible_payload()
    payload["scraps"][1]["id"] = "S1"
    resp = client.post("/api/solve", json=payload)
    assert resp.status_code == 422


def test_validation_bad_period():
    payload = feasible_payload()
    payload["scraps"][0]["period"] = 0
    resp = client.post("/api/solve", json=payload)
    assert resp.status_code == 422
