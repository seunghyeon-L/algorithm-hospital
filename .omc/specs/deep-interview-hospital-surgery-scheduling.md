# Deep Interview Spec: 병원 수술 스케줄링 — 그래프 알고리즘 비교 인터랙티브 웹 시뮬레이션

## Metadata
- Interview ID: di-hospital-surgery-scheduling-2026-06-02
- Rounds: 2 (+ Round 0 토폴로지 게이트)
- Final Ambiguity Score: 12.4%
- Type: greenfield
- Generated: 2026-06-02
- Threshold: 0.20 (20%)
- Threshold Source: default
- Initial Context Summarized: no
- Status: PASSED

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.90 | 0.40 | 0.360 |
| Constraint Clarity | 0.90 | 0.30 | 0.270 |
| Success Criteria | 0.82 | 0.30 | 0.246 |
| **Total Clarity** | | | **0.876** |
| **Ambiguity** | | | **0.124 (12.4%)** |

## Topology
| Component | Status | Description | Coverage / Deferral Note |
|-----------|--------|-------------|--------------------------|
| 문제 모델·데이터 | active | 수술·검사 30~50건을 DAG 노드로, 선후관계를 간선으로. 수술실 3개·의료진 한정 자원제약. PSPLIB + 합성 병원 작업 의존 그래프 | 입력 스키마·테스트 인스턴스 정의 필요 |
| 그래프 알고리즘 구현 | active | 교안: 위상정렬·DAG 최장경로·SCC / 최신: CPM·RCPSP·GA. 라이브러리 사용(알고리즘 재구현 X) | NetworkX, OR-Tools, DEAP |
| 시뮬레이션·성능비교 엔진 | active | 동일 인스턴스에 각 알고리즘 적용 후 총 대기시간·makespan 측정, "단순 순서 대비 N% 단축" 산출 | 핵심 채점 산출물 |
| 웹 UI/UX | active | FastAPI 백엔드 + React/Next.js 프론트엔드. 인터랙티브 시뮬레이션·시각화 | 스택 확정됨 |
| 확장요소 ABC | active | A: 2번째 최신기법 추가→3자 비교 / B: 추가 데이터셋으로 일반화 검증 / C: 미정의 | 최소 1개 필수(가능하면 전부). A+B 권장 |

## Goal
**한정된 수술실(3개)과 의료진으로 30~50건의 수술·검사를 스케줄링할 때, 선후행 제약을 그래프 알고리즘(위상정렬·DAG 최장경로/임계경로)으로 처리하고 자원제약을 메타휴리스틱(RCPSP·GA)으로 최적화하여, "단순 위상정렬 순서 대비 환자 총 대기시간이 몇 % 단축되는지"를 인터랙티브 웹에서 시각적으로 비교·시연하는 시스템을 구축한다.**

## Constraints
- 그래프 알고리즘 사용 필수 (교안: 위상정렬, DAG 최장경로, 강연결요소(SCC))
- 알고리즘을 "뜯어서" 재구현하지 않고, 검증된 라이브러리로 비교 중심 (NetworkX, DEAP, OR-Tools)
- 성능 개선 수치("얼마나 좋아졌는지")가 반드시 결과에 포함되어야 함
- 최종 산출물은 웹 기반 인터랙티브 시뮬레이션 (FastAPI + React/Next.js)
- 분량은 5인팀 기준 + α (확장요소 포함으로 충족)
- 참고자료는 기사/논문 모두 허용
- 확장요소 ABC 중 최소 1개 필수 (권장: A·B 모두)

## Non-Goals
- 알고리즘 자체의 새로운 변형/개선 발명 (비교가 목적, 재구현이 목적 아님)
- 실제 병원 시스템(EMR/HIS) 연동 또는 실시간 운영 배포
- 의료적으로 정밀한 수술 시간 추정 모델 (합성/공개 데이터로 충분)

## Acceptance Criteria
- [ ] 30~50건 작업 + 선후행 제약을 가진 DAG 인스턴스를 로드/생성할 수 있다 (PSPLIB + 합성)
- [ ] 위상정렬로 가능한 실행 순서와 DAG 최장경로(임계경로)를 계산해 표시한다
- [ ] 수술실 3개·의료진 한정 제약 하에서 RCPSP(OR-Tools)와 GA(DEAP)로 일정을 최적화한다
- [ ] 동일 인스턴스에서 베이스라인(단순 순서) vs RCPSP vs GA의 총 대기시간·makespan을 측정한다
- [ ] "단순 순서 대비 N% 단축" 형태의 성능 개선 수치를 산출·표시한다 (최소 3자 비교 = 확장요소 A)
- [ ] 웹 화면에서 인스턴스를 선택/조정하고 알고리즘별 결과 차이를 인터랙티브하게 비교할 수 있다 (간트차트·DAG 시각화)
- [ ] 추가 데이터셋(다른 규모/시나리오)으로 일반화 가능성을 검증한다 (확장요소 B)

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| "알고리즘 1개? 2개?" | 그래프 알고리즘 최종 선택 수 모호 | 베이스라인(위상정렬 순서 + greedy 자원배정) + RCPSP + GA의 3자 비교로 확정. ※ DAG 최장경로/CPM은 자원 무시 '참고용 하한'으로만 표시(스케줄러 베이스라인 아님) (확장요소 A 충족) |
| 웹 스택 미정 | 도구가 전부 Python인데 "웹으로 구현" | FastAPI(백엔드) + React/Next.js(프론트엔드)로 확정 |
| 확장요소 C 미정의 | A·B만 설명됨 | A·B 채택으로 필수요건 초과 충족, C는 추후 교안 확인 시 추가 |
| 목적함수 | "환자 대기 최소화" 추상적 | 1차: 총 대기시간(Σ 대기) / 보조: makespan으로 확정 |

## Technical Context (greenfield)
- **백엔드:** Python + FastAPI. 알고리즘 계층: NetworkX(위상정렬·최장경로·SCC), OR-Tools(RCPSP/CP-SAT), DEAP(GA)
- **프론트엔드:** React 또는 Next.js. 시각화: 간트차트, DAG 그래프, 알고리즘별 성능 비교 차트
- **데이터:** PSPLIB(표준 RCPSP 벤치마크), 합성 병원 작업 의존 그래프(30~50 작업, 수술실 3개)
- **핵심 연구 질문:**
  1. 수술·검사 30~50건에 선후관계가 있을 때, 위상정렬로 가능한 순서와 임계경로는 무엇인가?
  2. 수술실 3개·의료진 한정 시 총 대기시간을 최소화하는 일정을 메타휴리스틱으로 찾으면 단순 순서 대비 얼마나 단축되는가?

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| Task(수술·검사) | core domain | id, duration, resource_req | precedes other Tasks (DAG edge) |
| OperatingRoom(수술실) | resource | id, capacity(=3) | hosts Tasks |
| MedicalStaff(의료진) | resource | id, availability | assigned to Tasks |
| Patient(환자) | core domain | id, waiting_time | linked to Tasks |
| PrecedenceDAG | structure | nodes(Tasks), edges | topological order, longest/critical path |
| Schedule | output | task→(room, start, end) | produced by Algorithm |
| Algorithm | comparison subject | name(CPM/RCPSP/GA/Topo) | produces Schedule |
| Dataset | input | source(PSPLIB/synthetic), size | feeds PrecedenceDAG |
| Metric | evaluation | total_wait, makespan, %improvement | measured on Schedule |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|----------------|
| 0 (topology) | 4 | 4 | - | - | N/A |
| 1 (상세 답변) | 9 | 5 | 0 | 4 | 100% |
| 2 (스택) | 9 | 0 | 0 | 9 | 100% |

엔티티가 2라운드 연속 동일 → 도메인 모델 수렴 완료.

## Interview Transcript
<details>
<summary>Full Q&A (Round 0 + 2 rounds)</summary>

### Round 0 — 토폴로지
**Q:** 5개 상위 구성요소(문제모델/그래프알고리즘/시뮬레이션·비교/웹UI/확장요소ABC) 토폴로지가 맞나요?
**A:** 맞음 + ABC 상세 제공 — A: 2번째 최신기법 추가→3자 비교 / B: 추가 데이터셋으로 일반화 검증. 교안 알고리즘: 위상정렬·DAG최장경로·SCC. 최신기법: CPM·RCPSP·GA. 도구: PSPLIB·합성그래프 / NetworkX·DEAP·OR-Tools. 현실문제: 30~50건 선후관계 위상정렬·임계경로 / 수술실 3개·의료진 한정 시 메타휴리스틱으로 총 대기시간 단축률.

### Round 1
**Q:** 웹 스택을 무엇으로 할까요? (도구가 전부 Python)
**A:** FastAPI + React/Next.js
**Ambiguity:** 12.4% (Goal: 0.90, Constraints: 0.90, Criteria: 0.82)

</details>

---
**Status: pending approval**
