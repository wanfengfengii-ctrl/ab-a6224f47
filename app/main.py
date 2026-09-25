"""FastAPI 应用：健康检查、配片接口与前端静态资源。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import solver
from .schemas import SolveRequest

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="古籍补纸配片 API", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/solve")
def solve_endpoint(req: SolveRequest):
    damages = [
        solver.Damage(
            id=d.id,
            width=d.width,
            height=d.height,
            phase_min=d.phaseMin,
            phase_max=d.phaseMax,
        )
        for d in req.damages
    ]
    scraps = [
        solver.Scrap(
            id=s.id,
            x=s.region.x,
            y=s.region.y,
            width=s.region.width,
            height=s.region.height,
            period=s.period,
            origin=s.origin,
            max_uses=s.maxUses,
        )
        for s in req.scraps
    ]
    result = solver.solve(damages, scraps)

    if not result.feasible:
        ev = result.evidence
        return {
            "status": "infeasible",
            "evidence": {
                "constraint": ev.constraint,
                "damageIndex": ev.damage_index,
                "message": ev.message,
                "details": ev.details,
            },
        }

    sol = result.solution
    plan = []
    for p in sol.placements:
        d = req.damages[p.damage_index]
        s = req.scraps[p.scrap_index]
        plan.append(
            {
                "damageIndex": p.damage_index,
                "damageId": d.id,
                "scrapIndex": p.scrap_index,
                "scrapId": s.id,
                "start": p.start,
                "y": s.region.y,
                "width": d.width,
                "height": d.height,
                "leftPhase": p.left_phase,
                "rightPhase": p.right_phase,
            }
        )
    return {
        "status": "feasible",
        "objectives": {
            "scrapsUsed": sol.scraps_used,
            "usedRegionArea": sol.used_region_area,
            "piecesArea": sol.pieces_area,
            "wasteArea": sol.waste_area,
        },
        "plan": plan,
    }
