"use client";

import { useState, useEffect } from "react";
import type { CompareResponse, InstanceOut } from "./lib/api";
import { API_BASE, createInstance, compareAlgos } from "./lib/api";
import SummaryCards from "./components/SummaryCards";
import ComparisonChart from "./components/ComparisonChart";
import GanttChart from "./components/GanttChart";
import DagGraph from "./components/DagGraph";
import FloorPlan2D from "./components/FloorPlan2D";
import UtilizationChart from "./components/UtilizationChart";

// ---------------------------------------------------------------------------
// 파라미터 폼 상태
// ---------------------------------------------------------------------------

interface FormState {
  n_patients: number;
  seed: number;
  n_rooms: number;          // FOIA 실측 12 고정
  weighted: boolean;        // KTAS 가중 목적 on/off
  n_emergency: number;        // 0=정적 스케줄링, 1↑=동적 재스케줄
  time_limit_sec: number;
}

const DEFAULT_FORM: FormState = {
  n_patients: 20,
  seed: 42,
  n_rooms: 12,
  weighted: false,
  n_emergency: 0,
  time_limit_sec: 5,
};

// JNUH 규모 고정 자원 (사용자 변경 없이 모델 상수로 전달)
const FIXED = { n_staff: 24, n_anesthesia: 9, n_pacu: 18, turnover: 20 };

const ALGO_KEYS = ["baseline", "SA", "GA", "HGA", "CP-SAT"] as const;

const ALGO_COLORS: Record<string, string> = {
  baseline: "#6b7280",
  SA: "#f59e0b",
  "GA": "#16a34a",
  HGA: "#8b5cf6",
  "CP-SAT": "#2563eb",
};

const ALGO_KO: Record<string, string> = {
  baseline: "베이스라인",
  SA: "SA (담금질)",
  "GA": "GA",
  HGA: "HGA",
  "CP-SAT": "CP-SAT",
};

type TabKey = "floor" | "util" | "charts" | "gantt" | "dag";

const TAB_LABELS: Record<TabKey, string> = {
  floor: "🏥 동선 시뮬레이션",
  util: "📈 자원 가동률",
  charts: "📊 비교 차트",
  gantt: "📅 간트차트",
  dag: "🔗 DAG 그래프",
};

// ---------------------------------------------------------------------------
// 페이지 컴포넌트
// ---------------------------------------------------------------------------

export default function Home() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [instance, setInstance] = useState<InstanceOut | null>(null);
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("floor");

  function updateForm(key: keyof FormState, value: number | boolean) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleRun() {
    setLoading(true);
    setError(null);
    setResult(null);
    setInstance(null);
    try {
      // 1단계: JNUH 5단계 인스턴스 생성 (room=12 고정 등 모델 자원)
      const inst = await createInstance({
        n_patients: form.n_patients,
        seed: form.seed,
        n_rooms: form.n_rooms,
        n_staff: FIXED.n_staff,
        n_anesthesia: FIXED.n_anesthesia,
        n_pacu: FIXED.n_pacu,
        n_emergency: form.n_emergency,
        turnover: FIXED.turnover,
      });
      setInstance(inst);

      // 2단계: 5개 알고리즘 비교 (무가중 / KTAS 가중 선택)
      const cmp = await compareAlgos({
        instance_id: inst.instance_id,
        time_limit_sec: form.time_limit_sec,
        random_seed: form.seed,
        weighted: form.weighted,
      });
      setResult(cmp);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      const where = API_BASE ? `백엔드(${API_BASE})` : "백엔드";
      setError(
        `${where}에 연결할 수 없습니다. 로컬 개발이라면 백엔드를 먼저 실행하세요:\n` +
          `cd backend && uvicorn app.main:app --reload\n\n상세: ${msg}`
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      {/* 헤더 */}
      <header className="bg-white border-b px-6 py-4 flex items-center justify-between shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">JNUH 5단계 수술 스케줄링</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            PRECHECK∥PREP→SURG→REC→DISCHARGE · 수술실 12 · KTAS 가중 · baseline·SA·GA·HGA·CP-SAT
          </p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="/scheduling-handbook.html"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-semibold px-4 py-2 rounded-lg bg-violet-600 text-white hover:bg-violet-700 transition-colors whitespace-nowrap shadow-sm"
          >
            📖 수술 스케줄링 설명서
          </a>
          {instance && (
            <span className="text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded px-2 py-1 font-mono">
              {instance.instance_id}
            </span>
          )}
        </div>
      </header>

      <main className="max-w-[1800px] mx-auto px-6 py-6 space-y-6">
        {/* 파라미터 폼 */}
        <section className="bg-white rounded-xl border shadow-sm p-5">
          <h2 className="text-lg font-semibold mb-4">파라미터</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 items-end">
            <NumberField label="환자 수 (각 5단계)" min={5} max={40} step={1} value={form.n_patients} onChange={(v) => updateForm("n_patients", v)} />
            <NumberField label="시드 (재현용)" min={0} max={9999} step={1} value={form.seed} onChange={(v) => updateForm("seed", v)} />
            <NumberField label="시간예산 (초/알고리즘)" min={1} max={60} step={1} value={form.time_limit_sec} onChange={(v) => updateForm("time_limit_sec", v)} />
            <ToggleField label="목적함수" value={form.weighted} onText="KTAS 가중" offText="무가중 Σwait" onChange={(v) => updateForm("weighted", v)} />
            <NumberField label="응급 수 (0=정적·1↑=동적)" min={0} max={10} step={1} value={form.n_emergency} onChange={(v) => updateForm("n_emergency", v)} />
          </div>
          <p className="text-xs text-gray-400 mt-3">
            자원(제주대병원 정보공개 실측·2025): 수술실 12 · 마취 전문의 9 · 간호 주간 동시 ≈24(12실×2명; FOIA 43명 3교대·주간집중, 유사병원 유추) · 회복베드 18(추정) · 전환 20분.
            실제 <b>일평균 수술 ≈ 38건/일</b>(연 9,666건÷250 평일; 평일 평균 36.6건). 환자 수를 하루치(≈38) 안팎으로 두면 실제 운영에 가깝고, 그 부근에서 알고리즘 차이가 드러납니다.
          </p>
          <button
            onClick={handleRun}
            disabled={loading}
            className="mt-5 px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "실행 중…" : "비교 실행"}
          </button>
        </section>

        {/* 에러 */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm whitespace-pre-wrap">
            {error}
          </div>
        )}

        {/* 로딩 */}
        {loading && (
          <div className="bg-white rounded-xl border shadow-sm p-8 text-center text-gray-400">
            <div className="animate-spin inline-block w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full mb-3" />
            <p>알고리즘 실행 중… 알고리즘당 최대 {form.time_limit_sec}초가 걸릴 수 있습니다.</p>
          </div>
        )}

        {/* 결과 */}
        {result && instance && (
          <>
            {/* 요약 카드 */}
            <div className="bg-white rounded-xl border shadow-sm p-5">
              <SummaryCards data={result} />
            </div>

            {/* 탭 */}
            <div className="flex flex-wrap gap-2">
              {(["floor", "util", "charts", "gantt", "dag"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeTab === tab ? "bg-blue-600 text-white" : "bg-white border text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {TAB_LABELS[tab]}
                </button>
              ))}
            </div>

            {/* 동선 시뮬레이션 (2D 평면도) */}
            {activeTab === "floor" && (
              <div className="bg-white rounded-xl border shadow-sm p-5">
                <FloorPlan2D instance={instance} result={result} />
              </div>
            )}

            {/* 자원 가동률 */}
            {activeTab === "util" && (
              <div className="bg-white rounded-xl border shadow-sm p-5">
                <UtilizationChart data={result} instance={instance} />
              </div>
            )}

            {/* 비교 차트 */}
            {activeTab === "charts" && (
              <div className="bg-white rounded-xl border shadow-sm p-5">
                <ComparisonChart data={result} />
              </div>
            )}

            {/* 간트차트 */}
            {activeTab === "gantt" && (
              <div className="bg-white rounded-xl border shadow-sm p-5 space-y-6">
                <h2 className="text-xl font-semibold">간트차트 (수술실별 타임라인)</h2>
                {ALGO_KEYS.map((algo) => {
                  const res = result.results[algo];
                  if (!res) return null;
                  return (
                    <GanttChart
                      key={algo}
                      schedule={res.schedule}
                      title={`${ALGO_KO[algo]} — 대기 ${res.metrics.total_wait.toLocaleString()} · makespan ${res.metrics.makespan}분`}
                      accentColor={ALGO_COLORS[algo]}
                    />
                  );
                })}
              </div>
            )}

            {/* DAG 그래프 */}
            {activeTab === "dag" && (
              <div className="bg-white rounded-xl border shadow-sm p-5">
                <DagGraph instance={instance} criticalPath={result.critical_path} />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 재사용 숫자 입력 필드
// ---------------------------------------------------------------------------

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  // 입력칸을 문자열로 보유해 빈칸을 허용한다(0을 지울 수 있게).
  // 비운 채 두면 값은 0으로 처리하고, 포커스를 떠날 때 0을 채워 넣는다.
  const [text, setText] = useState<string>(String(value));
  useEffect(() => {
    // 외부에서 value가 바뀌면(리셋 등) 동기화 — 단, 현재 입력 숫자와 같으면 빈칸 유지
    const cur = text.trim() === "" ? 0 : Number(text);
    if (cur !== value) setText(String(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-gray-500">{label}</label>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={text}
        onChange={(e) => {
          const raw = e.target.value;
          setText(raw);
          onChange(raw.trim() === "" ? 0 : Number(raw));
        }}
        onBlur={() => {
          if (text.trim() === "") {
            setText("0");
            onChange(0);
          }
        }}
        className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
      />
    </div>
  );
}

function ToggleField({
  label,
  value,
  onText,
  offText,
  onChange,
}: {
  label: string;
  value: boolean;
  onText: string;
  offText: string;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-gray-500">{label}</label>
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`border rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
          value
            ? "bg-blue-600 text-white border-blue-600"
            : "bg-white text-gray-600 hover:bg-gray-50"
        }`}
      >
        {value ? onText : offText}
      </button>
    </div>
  );
}
