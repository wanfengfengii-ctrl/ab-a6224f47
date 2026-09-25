"""古籍补纸配片核心求解器。

领域规则（与 README 中的定义一致）：

* 边料 ``s`` 上位置 ``pos`` 处的水印相位为 ``(origin_s + pos) mod period_s``。
* 破损 ``d`` 的裁片宽 ``w_d``、高 ``h_d``，整数裁切起点 ``x`` 满足
  ``s.x <= x``、``x + w_d <= s.x + s.width``、``h_d <= s.height``。
* 裁片左缘相位必须落在破损要求的 ``[phase_min, phase_max]`` 内。
* 相邻破损（按输入顺序）前一处裁片右缘相位等于后一处裁片左缘相位。
* 同一边料上的裁片区间 ``[x, x + w)`` 不得重叠；
  边料 ``s`` 至多承载 ``max_uses_s`` 个裁片。

目标（按优先级依次比较）：

1. 使用的边料张数最少；
2. 裁切废料总面积最小（= 被使用边料的可裁区域总面积 - 全部裁片面积，
   由于裁片总面积固定，等价于最小化被使用边料的区域面积之和）；
3. 按破损输入顺序展开的 ``(边料序号, 裁切起点)`` 序列字典序最小。

不可行时按"尺寸越界 -> 相位范围不可达 -> 相邻相位不连续 -> 次数/重叠冲突"
的顺序返回首条约束证据。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


@dataclass(frozen=True)
class Damage:
    id: str
    width: int
    height: int
    phase_min: int
    phase_max: int


@dataclass(frozen=True)
class Scrap:
    id: str
    x: int
    y: int
    width: int
    height: int
    period: int
    origin: int
    max_uses: int

    @property
    def area(self) -> int:
        return self.width * self.height

    def phase_at(self, pos: int) -> int:
        return (self.origin + pos) % self.period


@dataclass(frozen=True)
class Placement:
    damage_index: int
    scrap_index: int
    start: int
    left_phase: int
    right_phase: int


@dataclass(frozen=True)
class Evidence:
    constraint: str
    damage_index: int
    message: str
    details: dict


@dataclass(frozen=True)
class Solution:
    placements: tuple
    scraps_used: int
    used_region_area: int
    pieces_area: int
    waste_area: int


@dataclass(frozen=True)
class SolveResult:
    feasible: bool
    solution: Optional[Solution] = None
    evidence: Optional[Evidence] = None


def feasible_starts(damage: Damage, scrap: Scrap) -> list:
    """破损 damage 在边料 scrap 上满足尺寸与相位范围的全部整数起点（升序）。"""
    if damage.height > scrap.height:
        return []
    lo = scrap.x
    hi = scrap.x + scrap.width - damage.width
    if hi < lo:
        return []
    return [
        x
        for x in range(lo, hi + 1)
        if damage.phase_min <= scrap.phase_at(x) <= damage.phase_max
    ]


def _group_by_phase(scrap: Scrap, xs: list) -> dict:
    groups: dict = {}
    for x in xs:
        groups.setdefault(scrap.phase_at(x), []).append(x)
    return groups


def _overlaps(intervals: list, x0: int, x1: int) -> bool:
    return any(a < x1 and x0 < b for a, b in intervals)


class _Search:
    """按三级目标做分支限界深度优先搜索。"""

    def __init__(self, damages: list, scraps: list, starts: dict):
        self.damages = damages
        self.scraps = scraps
        self.starts = starts
        self.starts_by_phase = {
            key: _group_by_phase(scraps[key[1]], xs) for key, xs in starts.items()
        }
        self.n = len(damages)
        self.m = len(scraps)
        self.use_count = [0] * self.m
        self.intervals: list = [[] for _ in range(self.m)]
        self.used_cnt = 0
        self.used_area = 0
        self.placements: list = []
        self.seq: list = []
        self.best_key: Optional[tuple] = None
        self.best_plan: Optional[list] = None
        # 仅用于不可行证据：记录搜索最深处的死胡同及其原因
        self.deepest_dead = -1
        self.deepest_reason: Optional[str] = None
        self._can_complete = self._make_oracle()

    def _make_oracle(self):
        """忽略重叠与可用次数，仅按相位连续性判断后缀是否可能排完（用于剪枝）。"""
        damages, scraps = self.damages, self.scraps
        starts, starts_by_phase = self.starts, self.starts_by_phase
        n, m = self.n, self.m

        @lru_cache(maxsize=None)
        def can(i: int, req: int) -> bool:
            if i == n:
                return True
            d = damages[i]
            for si in range(m):
                s = scraps[si]
                xs = starts[(i, si)] if req < 0 else starts_by_phase[(i, si)].get(req, ())
                for x in xs:
                    if can(i + 1, s.phase_at(x + d.width)):
                        return True
            return False

        return can

    def run(self) -> None:
        self._dfs(0)

    def _dfs(self, i: int) -> None:
        if i == self.n:
            key = (self.used_cnt, self.used_area, tuple(self.seq))
            if self.best_key is None or key < self.best_key:
                self.best_key = key
                self.best_plan = list(self.placements)
            return
        d = self.damages[i]
        req = -1 if i == 0 else self.placements[-1].right_phase
        if not self._can_complete(i, req):
            return
        had_candidate = False
        first_resource_reject: Optional[str] = None
        first_continuity_reject: Optional[str] = None
        for si, s in enumerate(self.scraps):
            if self.use_count[si] >= s.max_uses:
                if first_resource_reject is None:
                    first_resource_reject = (
                        f"边料 {s.id} 的可用次数已用尽（{s.max_uses} 次）"
                    )
                continue
            if req < 0:
                xs = self.starts[(i, si)]
            else:
                xs = self.starts_by_phase[(i, si)].get(req, ())
                if not xs and self.starts[(i, si)] and first_continuity_reject is None:
                    first_continuity_reject = (
                        f"边料 {s.id} 上没有左缘相位为 {req} 的整数起点"
                    )
            for x in xs:
                lp = s.phase_at(x)
                if _overlaps(self.intervals[si], x, x + d.width):
                    if first_resource_reject is None:
                        first_resource_reject = (
                            f"边料 {s.id} 上起点 {x} 处的裁片与已安排的裁片重叠"
                        )
                    continue
                if self._pruned(si, s, x):
                    continue
                had_candidate = True
                self._place(i, si, s, d, x, lp)
                self._dfs(i + 1)
                self._unplace(si, s, d, x)
        if not had_candidate and i > self.deepest_dead:
            self.deepest_dead = i
            self.deepest_reason = first_resource_reject or first_continuity_reject

    def _pruned(self, si: int, s: Scrap, x: int) -> bool:
        """相对当前最优解的分支限界（三级目标均为下界才允许剪枝）。"""
        if self.best_key is None:
            return False
        bk, ba, bseq = self.best_key
        new_cnt = self.used_cnt + (1 if self.use_count[si] == 0 else 0)
        if new_cnt > bk:
            return True
        new_area = self.used_area + (s.area if self.use_count[si] == 0 else 0)
        if new_cnt == bk and new_area > ba:
            return True
        if new_cnt == bk and new_area == ba:
            prefix = self.seq + [(si, x)]
            if prefix > list(bseq[: len(prefix)]):
                return True
        return False

    def _place(self, i: int, si: int, s: Scrap, d: Damage, x: int, lp: int) -> None:
        rp = s.phase_at(x + d.width)
        self.placements.append(Placement(i, si, x, lp, rp))
        self.seq.append((si, x))
        if self.use_count[si] == 0:
            self.used_cnt += 1
            self.used_area += s.area
        self.use_count[si] += 1
        self.intervals[si].append((x, x + d.width))

    def _unplace(self, si: int, s: Scrap, d: Damage, x: int) -> None:
        self.placements.pop()
        self.seq.pop()
        self.use_count[si] -= 1
        if self.use_count[si] == 0:
            self.used_cnt -= 1
            self.used_area -= s.area
        self.intervals[si].remove((x, x + d.width))


def solve(damages: list, scraps: list) -> SolveResult:
    """主入口：返回最优可行方案，或不可行时的首条约束证据。"""
    starts = {
        (i, si): feasible_starts(d, s)
        for i, d in enumerate(damages)
        for si, s in enumerate(scraps)
    }
    search = _Search(damages, scraps, starts)
    search.run()
    if search.best_key is not None:
        cnt, area, _ = search.best_key
        pieces = sum(d.width * d.height for d in damages)
        solution = Solution(
            placements=tuple(search.best_plan),
            scraps_used=cnt,
            used_region_area=area,
            pieces_area=pieces,
            waste_area=area - pieces,
        )
        return SolveResult(feasible=True, solution=solution)
    return SolveResult(
        feasible=False, evidence=_first_evidence(damages, scraps, starts, search)
    )


def _achievable_phases(damage: Damage, scrap: Scrap) -> set:
    """破损 damage 在边料 scrap 上所有可达的左缘相位集合。"""
    if damage.height > scrap.height:
        return set()
    lo = scrap.x
    hi = scrap.x + scrap.width - damage.width
    if hi < lo:
        return set()
    if hi - lo + 1 >= scrap.period:
        return set(range(scrap.period))
    return {scrap.phase_at(x) for x in range(lo, hi + 1)}


def _fmt(values, limit: int = 12) -> str:
    vals = list(values)
    if len(vals) > limit:
        return "[" + ", ".join(map(str, vals[:limit])) + ", …]"
    return "[" + ", ".join(map(str, vals)) + "]"


def _first_evidence(damages: list, scraps: list, starts: dict, search: _Search) -> Evidence:
    # 第一层：逐处破损检查尺寸与相位范围（与相邻关系无关）
    for i, d in enumerate(damages):
        if any(starts[(i, si)] for si in range(len(scraps))):
            continue
        fit = [s for s in scraps if d.width <= s.width and d.height <= s.height]
        if not fit:
            max_w = max(s.width for s in scraps)
            max_h = max(s.height for s in scraps)
            return Evidence(
                constraint="piece_exceeds_region",
                damage_index=i,
                message=(
                    f"破损 {d.id}（第 {i + 1} 处）所需裁片 {d.width}×{d.height} "
                    f"超出所有边料的可裁区域（现有最大可裁区域 {max_w}×{max_h}）"
                ),
                details={
                    "damageId": d.id,
                    "required": {"width": d.width, "height": d.height},
                    "maxRegion": {"width": max_w, "height": max_h},
                },
            )
        s = fit[0]
        achievable = sorted(_achievable_phases(d, s))
        return Evidence(
            constraint="phase_range_unreachable",
            damage_index=i,
            message=(
                f"破损 {d.id}（第 {i + 1} 处）要求左缘相位落在 "
                f"[{d.phase_min}, {d.phase_max}]，但任何边料都无法提供："
                f"例如边料 {s.id}（周期 {s.period}）上的可达相位为 {_fmt(achievable)}"
            ),
            details={
                "damageId": d.id,
                "phaseRange": [d.phase_min, d.phase_max],
                "scrapId": s.id,
                "period": s.period,
                "achievablePhases": achievable[:50],
            },
        )
    # 第二层：仅按相位连续性检查相邻衔接（忽略重叠与可用次数）
    n = len(damages)
    reachable: list = [set() for _ in range(n)]
    for si in range(len(scraps)):
        for x in starts[(0, si)]:
            reachable[0].add((si, x))
    for i in range(1, n):
        prev = damages[i - 1]
        rights = {scraps[si].phase_at(x + prev.width) for si, x in reachable[i - 1]}
        lefts: set = set()
        for si, s in enumerate(scraps):
            for x in starts[(i, si)]:
                lp = s.phase_at(x)
                lefts.add(lp)
                if lp in rights:
                    reachable[i].add((si, x))
        if not reachable[i]:
            return Evidence(
                constraint="phase_continuity",
                damage_index=i,
                message=(
                    f"破损 {prev.id} 与 {damages[i].id}（第 {i}–{i + 1} 处）之间水印相位无法衔接："
                    f"第 {i} 处右缘可达相位 {_fmt(sorted(rights))}，"
                    f"第 {i + 1} 处左缘可达相位 {_fmt(sorted(lefts))}，两者没有交集"
                ),
                details={
                    "prevDamageId": prev.id,
                    "damageId": damages[i].id,
                    "prevRightPhases": sorted(rights)[:50],
                    "leftPhases": sorted(lefts)[:50],
                },
            )
    # 第三层：边料可用次数 / 同料重叠导致的资源冲突
    idx = max(search.deepest_dead, 0)
    reason = search.deepest_reason or "边料可用次数与重叠约束组合后不存在可行安排"
    return Evidence(
        constraint="scrap_capacity_or_overlap",
        damage_index=idx,
        message=f"破损 {damages[idx].id}（第 {idx + 1} 处）无法安排：{reason}",
        details={"damageId": damages[idx].id, "reason": reason},
    )
