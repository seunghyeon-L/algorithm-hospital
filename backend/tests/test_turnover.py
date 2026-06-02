"""Turnover (room cleanup time) constraint tests.

전환시간(turnover): 같은 수술실에서 연속 케이스 사이에는 prev_end + turnover 이후에만
다음 케이스가 시작될 수 있다. baseline/RCPSP/GA 모두 이를 지켜야 한다(공정 비교).
turnover는 대기 정의(Σwait)에는 영향을 주지 않는다.
"""

from backend.app.data import generate_instance
from backend.app.baseline import schedule_baseline
from backend.app.rcpsp import schedule_rcpsp
from backend.app.ga import schedule_ga


def _room_turnover_ok(sched, instance) -> bool:
    """같은 방의 연속 케이스가 전환시간 간격을 지키는지 검사."""
    by_room: dict = {}
    for a in sched.assignments.values():
        by_room.setdefault(a.room, []).append((a.start, a.end))
    for ivs in by_room.values():
        ivs.sort()
        for i in range(1, len(ivs)):
            prev_end = ivs[i - 1][1]
            cur_start = ivs[i][0]
            if cur_start < prev_end + instance.turnover:
                return False
    return True


def test_turnover_field_default_zero():
    inst = generate_instance(n_tasks=10, seed=4)
    assert inst.turnover == 0


def test_baseline_respects_turnover():
    inst = generate_instance(n_tasks=15, seed=1, n_rooms=3, n_staff=6, turnover=30)
    sched = schedule_baseline(inst)
    sched.validate(inst)
    assert _room_turnover_ok(sched, inst)


def test_rcpsp_respects_turnover():
    inst = generate_instance(n_tasks=12, seed=2, n_rooms=2, n_staff=6, turnover=30)
    sched = schedule_rcpsp(inst, time_limit_sec=8)
    sched.validate(inst)
    assert _room_turnover_ok(sched, inst)


def test_ga_respects_turnover():
    inst = generate_instance(n_tasks=12, seed=3, n_rooms=2, n_staff=6, turnover=30)
    sched = schedule_ga(inst, seed=42, pop_size=30, n_gen=30)
    sched.validate(inst)
    assert _room_turnover_ok(sched, inst)


def test_turnover_increases_or_equals_makespan():
    """전환시간이 있으면 동일 인스턴스 대비 makespan이 줄어들지 않는다(자원이 더 빡빡)."""
    base = generate_instance(n_tasks=15, seed=7, n_rooms=2, n_staff=6, turnover=0)
    with_to = generate_instance(n_tasks=15, seed=7, n_rooms=2, n_staff=6, turnover=30)
    m0 = schedule_baseline(base).makespan()
    m1 = schedule_baseline(with_to).makespan()
    assert m1 >= m0
