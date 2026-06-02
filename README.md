---
title: 병원 수술 스케줄링 비교
emoji: 🏥
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

<!-- 위 YAML은 Hugging Face Spaces 설정용 frontmatter입니다(Docker SDK, 포트 7860). -->

# 병원 수술 스케줄링 — 그래프 알고리즘 비교 인터랙티브 웹 시뮬레이션

한정된 수술실(3개)·의료진으로 수술·검사 30~50건을 스케줄링하는 문제를,
**그래프 알고리즘**(위상정렬·DAG 최장경로/임계경로)과 **메타휴리스틱**(RCPSP·GA)으로 풀고,
동일 인스턴스에서 "단순 순서 대비 총 대기시간 N% 단축"을 측정해,
FastAPI + React/Next.js 인터랙티브 웹에서 비교·시연한다.

---

## 프로젝트 구조

```
hospital/
├── backend/
│   ├── app/
│   │   ├── model.py       # 공유 데이터 계약 (Instance / Schedule / Task)
│   │   ├── data.py        # 합성 DAG 생성기 + PSPLIB(.sm) 파서
│   │   ├── graph.py       # NetworkX 위상정렬·CPM·SCC
│   │   ├── baseline.py    # 위상정렬 + 자원제약(room+staff) greedy 디코더 (GA와 공유, naive 기준선)
│   │   ├── rcpsp.py       # OR-Tools CP-SAT 자원제약 스케줄링
│   │   ├── ga.py          # DEAP 유전 알고리즘
│   │   ├── metrics.py     # Σwait / makespan / 자원활용률 / %개선 계산
│   │   └── main.py        # FastAPI 라우터
│   ├── scripts/
│   │   └── run_generalization.py   # 확장요소 B: 일반화 검증 스크립트
│   └── tests/
│       ├── test_model.py
│       ├── test_data.py
│       ├── test_graph.py
│       ├── test_baseline.py
│       ├── test_metrics.py
│       ├── test_rcpsp.py
│       └── test_ga.py
├── frontend/              # Next.js 프론트엔드 (인터랙티브 시각화)
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## 비교 설계 원칙

### PINNED 목적함수 — 모든 알고리즘에 동일 적용

```
ready(task) = max(predecessor finish times)   # 선후행 제약만, 자원 무시. 선행 없으면 0.
wait(task)  = start(task) − ready(task)       # 자원 경합으로 인한 지연
헤드라인    = Σ_tasks wait(task)              # task-level 총 대기시간 (최소화 목표)
```

- **baseline**: 위상정렬 순서 + **자원제약(room+staff) greedy 디코더**. `Σwait`를 최소화하지 않는 의도적 naive 기준선. (GA와 동일 디코더 `greedy_resource_schedule`를 공유 → 공정 비교)
- **RCPSP** (OR-Tools CP-SAT): `Σwait` 최소화를 목적식으로 명시한 자원제약 스케줄링. 헤드라인 개선 보장.
- **GA** (DEAP): 동일 `Σwait`를 적합도로 사용. 품질보다 속도·확장성 축에서 평가.
- **CPM (임계경로)**: 자원 무시 DAG 최장경로 = 이론적 하한. **스케줄러가 아닌 참고 하한**으로만 표시.

### 공정 비교 구조

| 축 | 보장 방법 |
|---|---|
| 동일 인스턴스 | `data.py`의 고정 seed |
| 동일 목적식 | `model.py` 공유 타입 + `metrics.py` 단일 referee |
| **동일 자원제약** | baseline·GA·RCPSP 모두 **room + staff** 용량을 강제 (baseline.py의 공유 `greedy_resource_schedule`가 시간축 자원 프로파일을 검사; RCPSP는 CP-SAT `AddCumulative`). 세 알고리즘이 동일한 제약 문제를 푼다. |
| 동일 시간예산 | `RCPSP_TIME_LIMIT == GA_TIME_LIMIT` |
| 재현성 | CP-SAT `random_seed=42`, DEAP `random.seed(42)` |

---

## 대표 결과 (고정 시드, `run_generalization.py` 실측 — RCPSP 12s / GA 8s 예산)

| 시나리오 | N | Baseline Σwait | RCPSP Σwait | RCPSP 단축 | GA Σwait | GA 단축 |
|---|---|---|---|---|---|---|
| scale-n15   | 15 | 486  | 215 | **+55.8%** | 291 | +40.1% |
| scale-n30   | 30 | 885  | 355 | **+59.9%** | 426 | +51.9% |
| scale-n50   | 50 | 2162 | 974 | **+54.9%** | 836 | +61.3% |
| density-sparse | 30 | 5008 | 1944 | **+61.2%** | 1920 | +61.7% |
| density-dense  | 30 | 805  | 419 | **+48.0%** | 395 | +50.9% |
| rooms-tight (2실) | 30 | 1981 | 1041 | **+47.5%** | 1097 | +44.6% |
| rooms-relaxed (5실) | 30 | 1630 | 929 | **+43.0%** | 949 | +41.8% |
| seed-7-n40  | 40 | 275  | 100 | **+63.6%** | 100 | +63.6% |

> **일반화 검증(확장요소 B): 11/11 시나리오에서 RCPSP·GA 모두 baseline 대비 Σwait 개선(부호 일관). RCPSP 평균 +50.8% 단축.**
> 모든 알고리즘이 동일한 room+staff 제약을 지키므로 비교가 공정하다. 수치는 시간예산에 따라 달라지며, 재현하려면 아래 실행법 참고.

---

## 실행법

### 의존성 설치

```bash
pip install -r requirements.txt
```

### 백엔드 서버 실행

```bash
cd backend
uvicorn app.main:app --reload
# API 문서: http://localhost:8000/docs
```

### 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
# 브라우저: http://localhost:3000
```

### 테스트 전체 실행

```bash
# 프로젝트 루트에서
python -m pytest -q
```

### 확장요소 B — 일반화 검증

```bash
# 프로젝트 루트에서 전체 실행 (약 3~5분)
python -m backend.scripts.run_generalization

# 빠른 스모크 테스트 (QUICK=1, 약 30초)
QUICK=1 python -m backend.scripts.run_generalization

# 시간 예산 조정
RCPSP_TIME_LIMIT=10 GA_TIME_LIMIT=10 python -m backend.scripts.run_generalization
```

### API 엔드포인트 요약

| 엔드포인트 | 설명 |
|---|---|
| `GET /instances` | 사용 가능한 인스턴스 목록 |
| `POST /instances/generate` | 합성 인스턴스 생성 |
| `POST /schedule/{algo}` | 단일 알고리즘 실행 (`baseline`/`rcpsp`/`ga`) |
| `POST /compare` | 3자 동시 실행 + 지표 비교 반환 |

---

## 확장요소

### 확장요소 A — 3자 비교 (baseline vs RCPSP vs GA)

동일 인스턴스·동일 목적식·동일 시간예산에서 세 알고리즘을 비교.
`/compare` 엔드포인트가 단일 호출로 결과를 반환한다.

### 확장요소 B — 일반화 검증

`backend/scripts/run_generalization.py`가 다음 3개 축으로 ≥9개 시나리오를 실행한다:

- **규모 축**: n=15 / 30 / 50 태스크
- **밀도 축**: edge_prob=0.10 / 0.25 / 0.45 (희소·보통·밀도)
- **자원 압박 축**: n_rooms=2 / 3 / 5 (빡빡·보통·여유)

**합격 조건**: RCPSP의 `Σwait` 개선 부호(>0)가 모든 시나리오에서 일관 유지되면
"일반화 지지"로 보고. 미달 시 한계로 정직하게 보고.

---

## 배포 (Hugging Face Spaces — 단일 Docker)

프론트(Next.js 정적 export)와 백엔드(FastAPI)를 **하나의 Docker 컨테이너**로 묶어 같은 출처에서 서빙한다. 루트 `Dockerfile`이 ① Node로 프론트를 빌드(`out/`)하고 ② Python으로 FastAPI를 띄워 `/`에 정적 프론트를, 나머지 경로에 API를 매핑한다. (`README.md` 상단 YAML frontmatter가 Space 설정: `sdk: docker`, `app_port: 7860`)

```bash
# 1) huggingface.co 에서 New Space 생성 → SDK: Docker 선택
# 2) 이 저장소를 Space 원격에 푸시
git init && git add . && git commit -m "deploy"
git remote add space https://huggingface.co/spaces/<USER>/<SPACE>
git push space main        # 푸시하면 HF가 Dockerfile로 자동 빌드·배포

# (로컬에서 컨테이너 테스트)
docker build -t hospital-sched .
docker run -p 7860:7860 hospital-sched   # http://localhost:7860
```

배포본에서는 프론트가 API를 **상대경로**(같은 출처)로 호출하므로 CORS·주소 설정이 필요 없다(`NEXT_PUBLIC_API_BASE=""`로 빌드됨).

---

## 알고리즘 참고 자료

- Brucker et al., *Scheduling Algorithms*, 5th ed. — RCPSP 정의
- OR-Tools CP-SAT: https://developers.google.com/optimization/reference/python/sat/python/cp_model
- DEAP: https://deap.readthedocs.io/
- NetworkX DAG algorithms: https://networkx.org/documentation/stable/reference/algorithms/dag.html
- PSPLIB benchmark: http://www.om-db.wi.tum.de/psplib/
