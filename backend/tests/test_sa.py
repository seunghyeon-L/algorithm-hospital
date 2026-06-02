"""Simulated Annealing (SA) tests — fair-comparison metaheuristic."""

from backend.app.data import generate_instance
from backend.app.baseline import schedule_baseline
from backend.app.sa import schedule_sa


def test_sa_valid_schedule():
    inst = generate_instance(n_tasks=15, seed=1, n_rooms=3, n_staff=6, turnover=20)
    s = schedule_sa(inst, seed=42, max_iters=500)
    s.validate(inst)
    assert len(s.assignments) == len(inst.tasks)
    assert s.algo == "sa"


def test_sa_reproducible():
    inst = generate_instance(n_tasks=15, seed=2, n_rooms=3, n_staff=6)
    a = schedule_sa(inst, seed=7, max_iters=400)
    b = schedule_sa(inst, seed=7, max_iters=400)
    assert a.total_wait(inst) == b.total_wait(inst)


def test_sa_no_worse_than_baseline():
    """SA는 위상정렬(=baseline와 동일 출발점)에서 시작해 best만 유지하므로
    baseline보다 나빠질 수 없다."""
    inst = generate_instance(n_tasks=20, seed=3, n_rooms=3, n_staff=6, turnover=20)
    base = schedule_baseline(inst).total_wait(inst)
    sa = schedule_sa(inst, seed=42, max_iters=2000).total_wait(inst)
    assert sa <= base


def test_sa_respects_turnover():
    inst = generate_instance(n_tasks=12, seed=4, n_rooms=2, n_staff=6, turnover=30)
    s = schedule_sa(inst, seed=42, max_iters=300)
    by_room: dict = {}
    for a in s.assignments.values():
        by_room.setdefault(a.room, []).append((a.start, a.end))
    for ivs in by_room.values():
        ivs.sort()
        for i in range(1, len(ivs)):
            assert ivs[i][0] >= ivs[i - 1][1] + inst.turnover
