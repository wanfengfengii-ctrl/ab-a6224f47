"""求解器单元测试：约束、三级目标、字典序与不可行证据。"""
import itertools
import random

from app.solver import Damage, Scrap, feasible_starts, solve


def dmg(id, w, h, lo, hi):
    return Damage(id=id, width=w, height=h, phase_min=lo, phase_max=hi)


def scrp(id, x, y, w, h, period, origin, uses):
    return Scrap(
        id=id, x=x, y=y, width=w, height=h,
        period=period, origin=origin, max_uses=uses,
    )


def example_a():
    damages = [dmg("D1", 8, 10, 0, 5), dmg("D2", 8, 10, 0, 5), dmg("D3", 8, 10, 0, 5)]
    scraps = [
        scrp("S1", 0, 0, 40, 20, 6, 0, 3),
        scrp("S2", 0, 0, 30, 20, 6, 0, 1),
        scrp("S3", 5, 0, 30, 20, 6, 2, 1),
        scrp("S4", 0, 0, 25, 12, 6, 0, 1),
    ]
    return damages, scraps


def assert_plan_valid(damages, scraps, result):
    """校验返回方案满足全部业务约束。"""
    assert result.feasible
    sol = result.solution
    assert len(sol.placements) == len(damages)
    per_scrap = {}
    for idx, p in enumerate(sol.placements):
        assert p.damage_index == idx
        d = damages[p.damage_index]
        s = scraps[p.scrap_index]
        # 不越界
        assert s.x <= p.start
        assert p.start + d.width <= s.x + s.width
        assert d.height <= s.height
        # 相位计算与范围
        assert p.left_phase == (s.origin + p.start) % s.period
        assert p.right_phase == (s.origin + p.start + d.width) % s.period
        assert d.phase_min <= p.left_phase <= d.phase_max
        per_scrap.setdefault(p.scrap_index, []).append((p.start, p.start + d.width))
    # 可用次数与同料不重叠
    for si, ivs in per_scrap.items():
        assert len(ivs) <= scraps[si].max_uses
        ivs.sort()
        for (a0, a1), (b0, b1) in zip(ivs, ivs[1:]):
            assert a1 <= b0
    # 相邻相位连续
    for a, b in zip(sol.placements, sol.placements[1:]):
        assert a.right_phase == b.left_phase
    assert sol.scraps_used == len(per_scrap)
    assert sol.waste_area == sol.used_region_area - sol.pieces_area


def test_example_a_optimal_plan():
    damages, scraps = example_a()
    res = solve(damages, scraps)
    assert_plan_valid(damages, scraps, res)
    sol = res.solution
    # 仅 S1 可用次数 >= 3，故最少 1 张边料唯一可行
    assert sol.scraps_used == 1
    assert sol.used_region_area == 40 * 20
    assert sol.pieces_area == 3 * 8 * 10
    assert sol.waste_area == 800 - 240
    assert [(p.scrap_index, p.start) for p in sol.placements] == [(0, 0), (0, 8), (0, 16)]
    assert [p.left_phase for p in sol.placements] == [0, 2, 4]
    assert [p.right_phase for p in sol.placements] == [2, 4, 0]


def test_fewest_scraps_beats_smaller_area():
    # 1 张大边料（面积 1000）对比 3 张小边料（总面积 600）：张数优先
    damages = [dmg("D1", 10, 8, 0, 4), dmg("D2", 10, 8, 0, 4), dmg("D3", 10, 8, 0, 4)]
    scraps = [
        scrp("BIG", 0, 0, 100, 10, 5, 0, 3),
        scrp("A", 0, 0, 20, 10, 5, 0, 1),
        scrp("B", 0, 0, 20, 10, 5, 0, 1),
        scrp("C", 0, 0, 20, 10, 5, 0, 1),
    ]
    res = solve(damages, scraps)
    assert_plan_valid(damages, scraps, res)
    assert res.solution.scraps_used == 1
    assert res.solution.used_region_area == 1000
    assert [p.scrap_index for p in res.solution.placements] == [0, 0, 0]


def test_waste_area_tiebreak():
    # 同为 2 张边料时，选被用区域总面积更小者（{S1,S3}=500 优于 {S1,S2}=600）
    damages = [dmg("D1", 10, 8, 0, 4), dmg("D2", 10, 8, 0, 4), dmg("D3", 10, 8, 0, 4)]
    scraps = [
        scrp("S1", 0, 0, 30, 10, 5, 0, 2),
        scrp("S2", 0, 0, 30, 10, 5, 0, 2),
        scrp("S3", 0, 0, 20, 10, 5, 0, 2),
        scrp("S4", 0, 0, 50, 10, 5, 0, 1),
    ]
    res = solve(damages, scraps)
    assert_plan_valid(damages, scraps, res)
    sol = res.solution
    assert sol.scraps_used == 2
    assert sol.used_region_area == 500
    assert sol.waste_area == 500 - 3 * 80
    assert [(p.scrap_index, p.start) for p in sol.placements] == [(0, 0), (0, 10), (2, 0)]


def test_lexicographic_start_tiebreak():
    # 张数与面积均相同，取 (边料序号, 起点) 字典序最小：起点 5 优于 15
    damages = [dmg("D1", 5, 5, 0, 9), dmg("D2", 5, 5, 0, 9)]
    scraps = [
        scrp("S1", 0, 0, 30, 10, 10, 0, 2),
        scrp("S2", 0, 0, 4, 10, 10, 0, 1),
        scrp("S3", 0, 0, 4, 10, 10, 0, 1),
    ]
    res = solve(damages, scraps)
    assert_plan_valid(damages, scraps, res)
    assert [p.start for p in res.solution.placements] == [0, 5]


def test_overlap_forces_shift_on_same_scrap():
    # 周期 7、宽 7：第二片相位要求与第一片同余，必须平移避免重叠
    damages = [dmg("D1", 7, 5, 0, 6), dmg("D2", 7, 5, 0, 6)]
    scraps = [
        scrp("S1", 0, 0, 30, 10, 7, 0, 2),
        scrp("S2", 0, 0, 3, 10, 7, 0, 1),
        scrp("S3", 0, 0, 3, 10, 7, 0, 1),
    ]
    res = solve(damages, scraps)
    assert_plan_valid(damages, scraps, res)
    assert [p.start for p in res.solution.placements] == [0, 7]


def test_max_uses_forces_second_scrap():
    damages = [dmg("D1", 7, 5, 0, 6), dmg("D2", 7, 5, 0, 6)]
    scraps = [
        scrp("S1", 0, 0, 30, 10, 7, 0, 1),
        scrp("S2", 0, 0, 30, 10, 7, 0, 1),
        scrp("S3", 0, 0, 3, 10, 7, 0, 1),
    ]
    res = solve(damages, scraps)
    assert_plan_valid(damages, scraps, res)
    assert res.solution.scraps_used == 2
    assert [(p.scrap_index, p.start) for p in res.solution.placements] == [(0, 0), (1, 0)]


def test_phase_range_pins_start():
    damages = [dmg("D1", 4, 5, 3, 3)]
    scraps = [scrp("S1", 0, 0, 20, 10, 6, 0, 1)]
    res = solve(damages, scraps)
    assert_plan_valid(damages, scraps, res)
    assert res.solution.placements[0].start == 3
    assert res.solution.placements[0].left_phase == 3


def test_region_offset_respected():
    damages = [dmg("D1", 4, 5, 0, 10)]
    scraps = [scrp("S1", 5, 2, 10, 10, 6, 0, 1)]
    res = solve(damages, scraps)
    assert_plan_valid(damages, scraps, res)
    assert res.solution.placements[0].start == 5


def test_infeasible_piece_exceeds_region():
    damages = [dmg("D1", 50, 5, 0, 3)]
    scraps = [scrp("S1", 0, 0, 40, 20, 4, 0, 1), scrp("S2", 0, 0, 30, 10, 4, 0, 1)]
    res = solve(damages, scraps)
    assert not res.feasible
    assert res.evidence.constraint == "piece_exceeds_region"
    assert res.evidence.damage_index == 0
    assert "D1" in res.evidence.message


def test_infeasible_phase_range_unreachable():
    damages = [dmg("D1", 5, 5, 7, 9)]
    scraps = [scrp("S1", 0, 0, 10, 10, 4, 0, 2), scrp("S2", 0, 0, 10, 10, 4, 1, 1)]
    res = solve(damages, scraps)
    assert not res.feasible
    assert res.evidence.constraint == "phase_range_unreachable"
    assert res.evidence.damage_index == 0


def test_infeasible_phase_continuity():
    # S1 右缘相位 ∈ {0,1}，S2 左缘相位 = 2，两者不相交
    damages = [dmg("D1", 1, 3, 0, 9), dmg("D2", 1, 10, 0, 9)]
    scraps = [
        scrp("S1", 0, 0, 10, 5, 2, 0, 2),
        scrp("S2", 2, 0, 1, 20, 4, 0, 1),
    ]
    res = solve(damages, scraps)
    assert not res.feasible
    assert res.evidence.constraint == "phase_continuity"
    assert res.evidence.damage_index == 1


def test_infeasible_scrap_capacity():
    # 两处破损只能放在 S1 上，但 S1 可用次数为 1
    damages = [dmg("D1", 2, 2, 0, 1), dmg("D2", 2, 2, 0, 1)]
    scraps = [
        scrp("S1", 0, 0, 10, 10, 2, 0, 1),
        scrp("S2", 0, 0, 1, 1, 2, 0, 1),
    ]
    res = solve(damages, scraps)
    assert not res.feasible
    assert res.evidence.constraint == "scrap_capacity_or_overlap"
    assert res.evidence.damage_index == 1
    assert "S1" in res.evidence.message


def test_deterministic():
    damages, scraps = example_a()
    first = solve(damages, scraps)
    second = solve(damages, scraps)
    assert first == second


def _brute_force_key(damages, scraps):
    """小规模输入的暴力枚举，用于交叉验证求解器的三级目标。"""
    starts = {
        (i, si): feasible_starts(d, s)
        for i, d in enumerate(damages)
        for si, s in enumerate(scraps)
    }
    best = None
    per_damage = [
        [(si, x) for si in range(len(scraps)) for x in starts[(i, si)]]
        for i in range(len(damages))
    ]
    for combo in itertools.product(*per_damage):
        use = {}
        intervals = {}
        ok = True
        prev_right = None
        for i, (si, x) in enumerate(combo):
            s = scraps[si]
            d = damages[i]
            lp = s.phase_at(x)
            rp = s.phase_at(x + d.width)
            if prev_right is not None and lp != prev_right:
                ok = False
                break
            use[si] = use.get(si, 0) + 1
            if use[si] > s.max_uses:
                ok = False
                break
            for a, b in intervals.get(si, []):
                if a < x + d.width and x < b:
                    ok = False
                    break
            if not ok:
                break
            intervals.setdefault(si, []).append((x, x + d.width))
            prev_right = rp
        if not ok:
            continue
        area = sum(scraps[si].area for si in use)
        key = (len(use), area, tuple(combo))
        if best is None or key < best:
            best = key
    return best


def test_against_brute_force_random_small():
    rng = random.Random(20260925)
    for trial in range(120):
        n = rng.randint(2, 3)
        m = rng.randint(2, 4)
        damages = []
        for i in range(n):
            w = rng.randint(1, 4)
            lo = rng.randint(0, 4)
            damages.append(dmg(f"D{i}", w, rng.randint(1, 4), lo, lo + rng.randint(0, 3)))
        scraps = []
        for j in range(m):
            scraps.append(
                scrp(
                    f"S{j}",
                    rng.randint(0, 3),
                    0,
                    rng.randint(3, 10),
                    rng.randint(1, 5),
                    rng.randint(1, 5),
                    rng.randint(0, 4),
                    rng.randint(1, 3),
                )
            )
        res = solve(damages, scraps)
        expected = _brute_force_key(damages, scraps)
        if expected is None:
            assert not res.feasible, f"trial {trial}: 期望不可行"
        else:
            assert res.feasible, f"trial {trial}: 期望可行"
            assert_plan_valid(damages, scraps, res)
            got = (
                res.solution.scraps_used,
                res.solution.used_region_area,
                tuple((p.scrap_index, p.start) for p in res.solution.placements),
            )
            assert got == expected, f"trial {trial}: {got} != {expected}"
