"use client";

import { useState } from "react";
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
  n_tasks: number;
  seed: number;
  n_rooms: number;
  n_staff: number;
  turnover: number;
  time_limit_sec: number;
  ga_pop_size: number;
  ga_n_gen: number;
}

const DEFAULT_FORM: FormState = {
  n_tasks: 20,
  seed: 42,
  n_rooms: 3,
  n_staff: 5,
  turnover: 20,
  time_limit_sec: 10,
  ga_pop_size: 80,
  ga_n_gen: 100,
};

const ALGO_COLORS: Record<string, string> = {
  baseline: "#6b7280",
  rcpsp: "#2563eb",
  ga: "#16a34a",
  sa: "#f59e0b",
};

const ALGO_KO: Record<string, string> = {
  baseline: "베이스라인",
  rcpsp: "RCPSP",
  ga: "GA",
  sa: "SA",
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

  function updateForm(key: keyof FormState, value: number) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleRun() {
    setLoading(true);
    setError(null);
    setResult(null);
    setInstance(null);
    try {
      // 1단계: 인스턴스 생성
      const inst = await createInstance({
        n_tasks: form.n_tasks,
        seed: form.seed,
        n_rooms: form.n_rooms,
        n_staff: form.n_staff,
        edge_prob: 0.25,
        turnover: form.turnover,
      });
      setInstance(inst);

      // 2단계: 3자 비교 실행
      const cmp = await compareAlgos({
        instance_id: inst.instance_id,
        time_limit_sec: form.time_limit_sec,
        random_seed: form.seed,
        ga_pop_size: form.ga_pop_size,
        ga_n_gen: form.ga_n_gen,
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
          <h1 className="text-2xl font-bold text-gray-800">병원 수술 스케줄링</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            베이스라인 · RCPSP(CP-SAT) · GA(유전) · SA(담금질) — 총 대기시간(Σwait) 최소화
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
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7 gap-4">
            <NumberField label="작업 수" min={5} max={50} step={1} value={form.n_tasks} onChange={(v) => updateForm("n_tasks", v)} />
            <NumberField label="시드 (재현용)" min={0} max={9999} step={1} value={form.seed} onChange={(v) => updateForm("seed", v)} />
            <NumberField label="수술실 수" min={1} max={10} step={1} value={form.n_rooms} onChange={(v) => updateForm("n_rooms", v)} />
            <NumberField label="의료진 수" min={1} max={20} step={1} value={form.n_staff} onChange={(v) => updateForm("n_staff", v)} />
            <NumberField label="전환시간 (분)" min={0} max={60} step={5} value={form.turnover} onChange={(v) => updateForm("turnover", v)} />
            <NumberField label="시간예산 (초)" min={1} max={120} step={1} value={form.time_limit_sec} onChange={(v) => updateForm("time_limit_sec", v)} />
            <NumberField label="GA 개체수" min={10} max={500} step={10} value={form.ga_pop_size} onChange={(v) => updateForm("ga_pop_size", v)} />
            <NumberField label="GA 세대수" min={10} max={2000} step={10} value={form.ga_n_gen} onChange={(v) => updateForm("ga_n_gen", v)} />
          </div>
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
                {(["baseline", "rcpsp", "ga", "sa"] as const).map((algo) => {
                  const res = result.results[algo];
                  if (!res) return null;
                  return (
                    <GanttChart
                      key={algo}
                      schedule={res.schedule}
                      title={`${ALGO_KO[algo]} — 총 대기 ${res.metrics.total_wait}분 · makespan ${res.metrics.makespan}분`}
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
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-gray-500">{label}</label>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
      />
    </div>
  );
}
