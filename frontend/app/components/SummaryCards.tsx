"use client";

import type { CompareResponse } from "../lib/api";

const ALGO_LABELS: Record<string, string> = {
  baseline: "베이스라인 (그리디)",
  rcpsp: "RCPSP (CP-SAT)",
  ga: "GA (유전)",
  sa: "SA (담금질)",
};

const ALGO_COLORS: Record<string, string> = {
  baseline: "#6b7280",
  rcpsp: "#2563eb",
  ga: "#16a34a",
  sa: "#f59e0b",
};

interface Props {
  data: CompareResponse;
}

export default function SummaryCards({ data }: Props) {
  const algos = ["baseline", "rcpsp", "ga", "sa"] as const;

  return (
    <section>
      <h2 className="text-xl font-semibold mb-3">결과 요약</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {algos.map((algo) => {
          const res = data.results[algo];
          if (!res) return null;
          const m = res.metrics;
          const pct = m.pct_improvement_vs_baseline;
          const color = ALGO_COLORS[algo];
          return (
            <div
              key={algo}
              className="rounded-xl border p-4 shadow-sm"
              style={{ borderLeftColor: color, borderLeftWidth: 4 }}
            >
              <div className="text-sm font-medium text-gray-500 mb-1">
                {ALGO_LABELS[algo]}
              </div>
              <div className="text-2xl font-bold" style={{ color }}>
                {m.total_wait.toLocaleString()}분
              </div>
              <div className="text-xs text-gray-400 mb-2">총 대기시간 (Σwait)</div>
              <div className="text-sm text-gray-600">
                완료시각(makespan): <span className="font-medium">{m.makespan}분</span>
              </div>
              <div className="text-sm text-gray-600">
                실행시간: <span className="font-medium">{m.wall_clock_sec.toFixed(2)}초</span>
              </div>
              {pct !== null && pct !== undefined && (
                <div
                  className="mt-2 text-sm font-semibold"
                  style={{ color: pct > 0 ? "#16a34a" : pct < 0 ? "#dc2626" : "#6b7280" }}
                >
                  {pct > 0
                    ? `▼ 베이스라인 대비 대기 ${pct.toFixed(1)}% 감소`
                    : pct < 0
                    ? `▲ 베이스라인 대비 대기 ${Math.abs(pct).toFixed(1)}% 증가`
                    : "= 베이스라인과 동일"}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-3 text-sm text-gray-500">
        임계경로 길이 (자원 무시 이론적 하한):{" "}
        <span className="font-medium">{data.critical_path.length}분</span>{" "}
        · 경로 상 {data.critical_path.task_ids.length}개 작업
      </div>
    </section>
  );
}
