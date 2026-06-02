# Deep Interview Spec: 의료 현장 리서치 기반 설명서 + 자원 가동률 시각화 + 리서치 주도 코드 보완

## Metadata
- Interview ID: di-medical-research-explainer-2026-06-02
- Rounds: 3 (+ Round 0 토폴로지)
- Final Ambiguity Score: ~15%
- Type: brownfield (기존 hospital 프로젝트 확장)
- Generated: 2026-06-02
- Threshold: 0.20 (20%)
- Threshold Source: default
- Status: PASSED

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal | 0.88 | 0.35 | 0.308 |
| Constraints | 0.85 | 0.25 | 0.2125 |
| Success Criteria | 0.78 | 0.25 | 0.195 |
| Context | 0.90 | 0.15 | 0.135 |
| **Total / Ambiguity** | | | **0.85 / 0.15** |

## Topology
| Component | Status | Description | Coverage |
|-----------|--------|-------------|----------|
| 자원 가동률 시각화 | active | 의료진·수술실 가동률을 웹앱에 추가 | 알고리즘별 가동률 막대 + 시간대별 가동률 차트 (핵심 위주, 구현자 재량) |
| 설명서 웹페이지 | active | 독립 HTML 설명서 | 실제 논문 출처·링크 포함 필수 |
| 코드 보완 | active | 리서치 주도 incremental 반영 | 조사 결과 가치 있는 것만, 큰 변경은 사전 제안 후 적용 |
| (리서치) | 횡단 입력 | 실제 의료 현장 방식 + 최신 기법 조사 | 2·3의 공통 입력, WebSearch로 실제 자료 |

## Goal
**실제 병원 수술 스케줄링 현장 방식과 최신 스케줄링 기법(논문)을 웹 리서치로 조사하고, 그 결과를 (1) 출처·링크가 포함된 독립 HTML "설명서"로 정리하며, (2) 의료진·수술실 가동률 시각화를 웹앱에 추가하고, (3) 조사 결과 코드에 반영할 가치가 있는 것을 제안·적용한다.**

## Constraints
- 리서치는 **실제 자료 기반** — WebSearch/WebFetch로 실제 논문·기사·가이드라인을 찾고 설명서에 출처/링크를 명시
- 설명서는 **독립 HTML 페이지** (concept-map.html과 동일 톤·스타일, 오프라인에서 열림, 한글)
- 가동률 시각화는 기존 `metrics.resource_utilization`을 활용, 외부 차트 라이브러리 없이 순수 SVG/div (기존 패턴 유지)
- 코드 보완은 **리서치 주도·재량** — 큰 모델 변경(새 제약/알고리즘)은 사전에 사용자에게 구체안 제안 후 승인받아 적용
- 기존 백엔드 테스트(134개) 그린 유지, 프론트 `npm run build` 통과 유지
- 공정 비교 원칙(동일 Σwait 목적식·동일 room+staff 제약) 깨지 않기

## Non-Goals
- 실제 병원 EMR/HIS 연동
- 의료적으로 정밀한 수술시간 예측 모델
- 사전 승인 없는 대규모 알고리즘 재작성

## Acceptance Criteria
- [ ] 실제 의료 현장 수술 스케줄링 방식을 웹 리서치로 조사하고 출처를 확보한다 (병원 운영 가이드/기사/논문)
- [ ] 최신 스케줄링 기법(메타휴리스틱·정수계획·강화학습·다목적 등)을 논문 기준으로 조사하고 출처를 확보한다
- [ ] 설명서 HTML이 다음을 모두 포함: ① 실제 의료 현장 방식 ② 알고리즘 landscape(각 알고리즘이 무엇인지) ③ 각 알고리즘의 트레이드오프 ④ 이 프로젝트에 어떻게 적용 가능한지 ⑤ 최종 선택과 근거 ⑥ 반영한 최신 논문(제목·출처·링크)
- [ ] 가동률 시각화: 알고리즘별 수술실·의료진 가동률 막대 + 시간대별 가동률 차트를 웹앱 새 탭으로 추가
- [ ] 가동률 수치가 백엔드 `metrics`(resource_utilization)와 일치한다
- [ ] 코드 보완: 조사에서 도출한 개선안을 사용자에게 제안하고, 승인된 항목을 반영하되 134 테스트 그린·빌드 통과 유지
- [ ] 설명서의 모든 출처는 실제 접근 가능한 링크/서지정보를 가진다 (허위 인용 금지)

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| "코드에 적용" 범위 | 새 알고리즘? 제약? 지표? | 리서치 주도·재량 — 가치 있는 것만, 큰 변경은 사전 제안 후 적용 |
| 설명서 형태 | 독립 HTML vs 앱 내 페이지 | 독립 HTML (concept-map.html 스타일) |
| 가동률 뷰 범위 | 어떤 차트? | 구현자 재량 — 알고리즘별 막대 + 시간대별 차트 핵심 |
| 리서치 신뢰성 | 지식 기반 vs 실제 조사 | 실제 WebSearch 조사 + 출처/링크 명시, 허위 인용 금지 |

## Technical Context (brownfield)
- 백엔드: `backend/app/` — model/data/graph/baseline/rcpsp/ga/metrics/main(FastAPI). `metrics.evaluate()`가 이미 `resource_utilization: Dict[str,float]` 산출.
- 프론트: `frontend/` Next.js 정적 export, 컴포넌트 SummaryCards/ComparisonChart/GanttChart/DagGraph/FloorPlan2D(순수 SVG/CSS). page.tsx 탭 구조.
- 기존 설명서: 루트 `concept-map.html` (독립 HTML, 한글, 카드/배지 스타일) — 새 설명서의 디자인 기준.
- 배포: HF Spaces 단일 Docker(정적 프론트 + FastAPI). 가동률 탭은 프론트에 추가 → 재빌드·재스테이징 필요.

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| 가동률(Utilization) | metric | room_util%, staff_util%, over_time | metrics.resource_utilization에서 파생 |
| 설명서(Handbook) | deliverable | 현장방식·landscape·트레이드오프·선택·논문 | 독립 HTML |
| 리서치 출처(Citation) | external | title, authors, url/venue | 설명서·코드 보완 근거 |
| 최신 기법(Technique) | concept | 이름, 분류, 트레이드오프, 적용성 | 설명서 landscape 항목 |
| 코드 개선안(Enhancement) | proposal | 항목, 가치, 난이도, 적용여부 | 리서치에서 도출 |

## Research Scope (실제 조사 대상)
- **현장 방식**: 수술실 운영(OR scheduling/block scheduling), 전환시간(turnover), 응급/추가 수술 삽입, 외과의·마취·간호 인력 제약, 가동률(OR utilization) KPI
- **최신 기법**: 정수계획(MILP), 제약프로그래밍(CP-SAT), 메타휴리스틱(GA/SA/Tabu/PSO), 다목적(NSGA-II), 강화학습 기반 스케줄링, 로버스트/확률적 스케줄링 — 각 트레이드오프와 적용성

## Interview Transcript
<details><summary>Q&A (Round 0 + 3 rounds)</summary>

### Round 0 — 토폴로지
A: 3개 구성요소 확정(가동률 시각화 / 설명서 HTML / 코드 보완), 리서치는 공통 입력.

### Round 1 — 코드 보완 범위
A: "실제로 조사해서 현재 병원 수술 스케줄링 방식·최신 기법을 알아내고, 그 조사를 토대로 코드에 넣을 가치가 있으면 넣어라" → 리서치 주도·재량.

### Round 2 — 설명서 형태
A: 독립 HTML 페이지 (실제 출처·링크 포함).

### Round 3 — 가동률 뷰
A: 알아서 핵심 위주로 → 알고리즘별 막대 + 시간대별 차트.
**Ambiguity:** ~15%
</details>

---
**Status: pending approval**
