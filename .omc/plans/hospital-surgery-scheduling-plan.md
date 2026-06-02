# Work Plan: 병원 수술 스케줄링 — 그래프 알고리즘 비교 인터랙티브 웹 시뮬레이션

**Source spec:** `.omc/specs/deep-interview-hospital-surgery-scheduling.md`
**Status:** pending approval (consensus reached: Architect + Critic)

## Requirements Summary
한정된 수술실(3개)·의료진으로 수술·검사 30~50건을 스케줄링하는 문제를, 그래프 알고리즘(위상정렬·DAG 최장경로/임계경로)과 메타휴리스틱(RCPSP·GA)으로 풀고, 동일 인스턴스에서 "단순 순서 대비 총 대기시간 N% 단축"을 측정해, FastAPI + React/Next.js 인터랙티브 웹에서 비교·시연한다.

## RALPLAN-DR Summary (short mode)

### Principles (4)
1. **비교가 목적, 재구현이 아니다** — 알고리즘은 검증된 라이브러리(NetworkX/OR-Tools/DEAP) 사용, 새 변형 발명 금지
2. **공정한 비교** — 모든 알고리즘은 동일 인스턴스·동일 목적함수·동일 자원제약에서 평가
3. **재현성** — 합성 데이터 생성에 시드 고정, 결과 수치는 동일 입력에서 재현 가능
4. **점진적 산출** — 백엔드 알고리즘→비교엔진→API→프론트 순으로 각 단계가 독립 검증 가능

### Decision Drivers (top 3)
1. 그래프 알고리즘 필수 + 성능 개선 수치 필수 (교수 요구)
2. 5인팀 + α 분량 → 확장요소 A(3자 비교)·B(추가 데이터셋) 포함
3. 도구가 전부 Python → 백엔드 Python, 프론트는 별도 JS 계층

### Viable Options (≥2)
**Option 1 — FastAPI(Python) + React/Next.js (확정/채택)**
- Pros: 알고리즘 라이브러리 직접 사용, UI/UX 자유도 최대, 분량 조건(+α) 충족, REST로 백/프론트 분리
- Cons: 풀스택 구성 난이도·작업량 큼, 프론트 시각화 직접 구현 필요

**Option 2 — Streamlit (단일 Python) [기각]**
- Pros: 구현 빠름, 알고리즘과 바로 연결
- Cons: 인터랙티브·UI/UX 자유도 제한, "+α 분량" 어필 약함
- **Invalidation rationale:** 인터뷰에서 사용자가 FastAPI+React/Next.js를 명시 선택. Streamlit은 분량·UI 자유도 요구를 충족하지 못함

## Objective Function (PINNED — single definition for all algorithms)
> 공정 비교(Principle 2)를 코드로 강제하기 위해, 아래 정의를 CP-SAT 목적식·GA 적합도·metrics 측정에 **글자 그대로 동일하게** 사용한다.
- `ready(task)` = 모든 선행 작업의 **완료 시각의 최댓값** (선후행 제약만 고려, 자원 미고려). 선행 없으면 0.
- `wait(task)` = `start(task) − ready(task)` (자원 경합으로 인한 지연을 포착)
- **헤드라인 지표 = Σ_over_tasks wait(task)** — 작업 단위 총 대기시간 (task-level로 명시). 환자 단위가 아님.
  - (선택) 환자 단위 보고가 필요하면 `patient_wait = 환자의 마지막 작업 완료시각 − 환자 최초 ready`로 별도 정의·표기. 헤드라인은 task-level 고정.
- **보조 지표:** makespan(전체 완료 시각), 자원 활용률, wall-clock 실행시간
- CP-SAT 목적식과 GA 적합도는 모두 `Σ wait(task)` 최소화로 **동일**. baseline은 이 값을 최소화하지 않는 의도적 naive 기준선.

## Architecture Overview
```
[Frontend: React/Next.js]
  - 인스턴스 선택/파라미터 조정 (작업 수, 수술실 수, 시드)
  - DAG 시각화, 알고리즘별 간트차트, 성능 비교 차트
        │  REST (JSON)
[Backend: FastAPI]
  /instances        : 데이터셋 목록/생성 (PSPLIB, 합성)
  /schedule/{algo}  : 알고리즘 실행 → 일정 반환
  /compare          : 여러 알고리즘 동시 실행 → 지표 비교
        │
[Algorithm layer (Python)]
  - model.py    : 공유 데이터 계약 — Instance, Schedule(task→{room,start,end}) 단일 타입.
                  모든 알고리즘이 동일 Schedule을 산출하고 metrics가 동일 타입을 소비 (공정성 구조적 강제)
  - graph.py    : NetworkX 위상정렬, DAG 최장경로(임계경로), SCC(사이클 검출)
                  ※ 최장경로/CPM = 자원 무시 '도달 불가 하한(reference lower bound)'. 스케줄러 베이스라인 아님
  - baseline.py : 위상정렬 순서 + 그리디 자원배정 → 비교 가능한 베이스라인 스케줄러
  - rcpsp.py    : OR-Tools CP-SAT 자원제약 스케줄링 (random_seed 고정)
  - ga.py       : DEAP 유전 알고리즘 일정 배정 (random RNG 시드 고정)
  - metrics.py  : Σ wait(task), makespan, 자원활용률, wall-clock 시간, %개선 계산
  - data.py     : PSPLIB 파서 + 합성 병원 의존그래프 생성기(시드)
```

## Implementation Steps

### Phase A: 백엔드 — 데이터 계약 & 그래프 기반 (교안 알고리즘)
0. `model.py`: `Instance`(작업·선후행·소요·자원), `Schedule`(task→{room,start,end}) 공유 타입 정의. 모든 알고리즘 출력·metrics 입력의 단일 계약
1. `data.py`: 합성 병원 작업 의존 그래프 생성기 (30~50 작업, 선후관계, 소요시간, 자원요구, **시드 고정**) + PSPLIB(.sm) 파서
2. `graph.py`: NetworkX로 (a) 위상정렬 가능 순서, (b) DAG 최장경로=임계경로(**자원 무시 하한, 참고용**), (c) SCC로 사이클(불가능 제약) 검출
3. `baseline.py`: 위상정렬 순서를 따르되 수술실 3개·의료진 제약 하 그리디 배정 → 비교 기준 일정(naive)
4. `metrics.py`: 일정 → **Σ wait(task)** (PINNED 정의), makespan, 자원 활용률, **wall-clock 실행시간**, %개선 산출

### Phase B: 백엔드 — 최신 기법 (메타휴리스틱)
5. `rcpsp.py`: OR-Tools CP-SAT로 자원제약 스케줄링(수술실=용량 자원), 목적=**Σ wait(task) 최소화**(PINNED와 동일식), `time_limit`·`random_seed` 고정
6. `ga.py`: DEAP로 작업 우선순위/배정 인코딩, 적합도=**Σ wait(task)**(제약 위반 페널티), **RNG 시드 고정**, CP-SAT와 동일 wall-clock 예산 하 실행
7. 3자(베이스라인 vs RCPSP vs GA) 동일 인스턴스·동일 목적식·동일 시간예산 비교 → 확장요소 A 충족

### Phase C: API 계층
8. FastAPI 라우터: `/instances`, `/schedule/{algo}`, `/compare`. Pydantic 스키마로 입출력 정의
9. `/compare`가 동일 인스턴스에 N개 알고리즘 실행 후 지표·일정·%개선을 한 번에 반환

### Phase D: 프론트엔드
10. Next.js 프로젝트: 인스턴스 선택/파라미터 폼, 실행 버튼
11. 시각화: DAG 그래프(임계경로 강조), 알고리즘별 간트차트, 총대기시간·makespan 비교 막대/선 차트
12. 인터랙티브: 작업 수/수술실 수/시드 조정 시 재실행하여 차이 시연

### Phase E: 확장요소 & 마무리
13. 확장요소 B: 다른 규모/시나리오 데이터셋(예: 대규모 PSPLIB 또는 다른 합성 분포) 추가 → 일반화 검증 결과 표
14. (선택) 확장요소 C: 교안 확인 후 추가 (예: 추가 지표 또는 추가 알고리즘)
15. 결과 리포트: "단순 순서 대비 RCPSP N%, GA M% 단축" 요약 + 참고 논문/기사 인용

## Acceptance Criteria (testable)
- [ ] `data.py`가 시드 고정 시 동일한 30~50작업 DAG를 재현 생성한다 (unit test)
- [ ] `model.py`의 `Schedule` 타입을 baseline/RCPSP/GA 세 알고리즘이 모두 동일하게 산출한다 (type/shape 테스트)
- [ ] `graph.py`가 사이클 없는 DAG에 대해 위상정렬 순서를 반환하고, 알려진 소형 예제에서 임계경로 길이가 수기 계산과 일치한다
- [ ] `graph.py`가 사이클이 있는 입력에서 SCC로 불가능을 감지한다
- [ ] 동일 인스턴스에서 baseline/RCPSP/GA 3자 모두 유효한(제약 위반 없는) 일정을 산출한다
- [ ] `metrics.py`의 `Σ wait(task)`·makespan·wall-clock·%개선 산출값이 소형 예제에서 수기 계산과 일치한다
- [ ] **RCPSP는** 고정 시드 인스턴스 세트(≥3개)에서 baseline 대비 `Σ wait`를 **엄격히 감소**시킨다(% 개선 > 0)
- [ ] **GA는** 고정 시드에서 baseline 대비 개선하되, 미달 시 이를 정직한 결과로 보고하고 **GA의 합격 축은 동일 시간예산 내 실행시간/확장성**으로 명시한다
- [ ] `/compare` 엔드포인트가 단일 호출로 3자 비교 결과(JSON)를 반환한다
- [ ] 프론트에서 파라미터 변경 후 재실행 시 DAG·간트·비교차트가 갱신된다
- [ ] 확장요소 B: ≥2개 규모/시나리오 데이터셋에서 **개선 부호(>0)가 동일하게 유지**되는지로 일반화를 검증한다(반증 가능 조건). 유지되면 일반화 지지, 아니면 한계로 보고

## Risks and Mitigations
| Risk | Mitigation |
|------|-----------|
| GA(DEAP)가 baseline보다 나쁜 결과 → "개선" 서사 깨짐 | RCPSP(OR-Tools)가 개선을 보장하므로 헤드라인은 RCPSP로 입증. GA는 "동일 예산 내 속도/확장성" 축으로 정직 보고 |
| GA 확률성 → 재현 불가(Principle 3 위반) | DEAP `random` RNG 시드 고정. 보고 수치는 고정 시드 1개 또는 K개 시드 mean±std |
| OR-Tools 대규모(50작업)에서 시간 초과 | `time_limit` 설정 + best-found 사용, 인스턴스 규모 단계화. GA도 동일 wall-clock 예산 적용(공정) |
| 합성 데이터가 비현실적 | PSPLIB 표준 벤치마크 병행으로 신뢰성 확보 |
| 풀스택 작업량 과다(팀) | 백엔드(공정 비교)를 hard 선행 마일스톤으로 완료 후 프론트는 핵심 3개 시각화로 범위 고정 |
| 목적함수 정의 모호 | 상단 **Objective Function (PINNED)** 섹션으로 task-level `Σ wait(task)` 단일 정의, 3 알고리즘 동일 적용 |

## Verification Steps
1. `pytest`로 model/graph/metrics 단위 테스트 (소형 예제 정답 대조, Schedule 타입 일치)
2. 소형(10작업) 인스턴스에서 손계산 `Σ wait` vs 코드 결과 대조
3. **고정 시드** 인스턴스 세트(≥3)에서 RCPSP의 %개선 > 0을 통합 테스트로 확인 (GA는 시드 고정 후 보고; 합격 조건은 동일 예산 내 실행시간)
4. 프론트 E2E: 파라미터 변경→재실행→차트 갱신 수동 확인
5. PSPLIB 알려진 인스턴스에서 makespan이 합리적 범위인지 점검
6. 확장요소 B: ≥2 데이터셋에서 개선 부호 일관성 확인

## ADR
- **Decision:** FastAPI(Python) + React/Next.js 풀스택으로, 교안 그래프 알고리즘(위상정렬·DAG 최장경로·SCC, 참고용 임계경로 하한)과 메타휴리스틱(RCPSP via OR-Tools, GA via DEAP)을 동일 인스턴스·동일 `Σ wait(task)` 목적식·동일 시간예산에서 3자 비교하는 인터랙티브 웹 시뮬레이션을 구축한다.
- **Drivers:** (1) 그래프 알고리즘+성능 개선 수치 필수, (2) 5인팀+α 분량 → 확장요소 A·B, (3) 도구 전부 Python.
- **Alternatives considered:** Streamlit 단일 Python(빠르나 UI/분량 약함 — 인터뷰에서 스택 명시로 기각); 헤드라인을 makespan으로(자원 무시 하한과 혼동 위험 — task-level Σwait로 기각); CPM을 베이스라인 스케줄러로(자원제약 무시로 비교 불가 — 참고 하한으로 강등).
- **Why chosen:** 사용자 명시 스택 + 분량 조건 충족, RCPSP가 개선 보장으로 헤드라인 신뢰성 확보, 공정성을 `model.py` 공유 타입·PINNED 목적식·동일 예산으로 구조적 강제.
- **Consequences:** 풀스택 작업량 증가 → 백엔드 공정 비교를 hard 선행 마일스톤으로 게이트, 프론트 범위는 핵심 3개 시각화로 캡. GA는 품질이 아닌 속도/확장성 축으로 정직 보고.
- **Follow-ups:** 확장요소 C 정의(교안 확인); 환자 단위 보고 필요 시 patient_wait 집계 규칙 추가; PSPLIB 라이선스/형식 확인.

## Changelog (consensus improvements applied)
Architect(SOUND WITH CHANGES) + Critic(APPROVE WITH IMPROVEMENTS) 합의로 7개 개선 반영:
1. **목적함수 고정** — `Objective Function (PINNED)` 섹션 신설, task-level `Σ wait(task)`를 CP-SAT·GA·metrics 동일 적용 [Architect#1/Critic#1]
2. **CPM 재라벨링** — 최장경로/CPM = 자원 무시 참고 하한, 베이스라인은 greedy list-scheduling으로 명시 [#2]
3. **`model.py` 공유 데이터 계약** 추가(Instance/Schedule) — 공정성 구조적 강제 [#3]
4. **wall-clock 시간 측정 + CP-SAT/GA 동일 시간예산** 추가 [#4]
5. **반증 가능 AC** — GA의 vacuous "≤" 제거, 확장요소 B에 부호 일관성 합격조건 부여 [#5]
6. **GA 재현성** — DEAP/OR-Tools 시드 고정(Principle 3 충족) [Critic#6, Architect 누락분]
7. **검증 단계 수정** — flaky/vacuous 통합테스트를 고정 시드 + RCPSP %개선>0으로 재정의 [Critic#7]

**Status: pending approval** (consensus 도달 — Critic 승인 + 개선 반영 완료)
