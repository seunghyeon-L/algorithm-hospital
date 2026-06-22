"use client";

// UtilizationChart — 자원 가동률 시각화.
// ① 알고리즘별 수술실·의료진 가동률 막대 (metrics.resource_utilization)
// ② 선택 알고리즘의 시간대별 동시 사용량(가동률) 곡선 — schedule에서 계산
// 순수 SVG/div, 외부 라이브러리 없음.

import { useMemo, useState } from "react";
import type { CompareResponse, InstanceOut } from "../lib/api";

type AlgoKey = "baseline" | "SA" | "GA" | "HGA" | "CP-SAT";
const ALGO_LABELS: Record<AlgoKey, string> = {
  baseline: "베이스라인",
  SA: "SA",
  "GA": "GA",
  HGA: "HGA",
  "CP-SAT": "CP-SAT",
};
const ALGO_COLORS: Record<AlgoKey, string> = {
  baseline: "#9ca3af",
  SA: "#f59e0b",
  "GA": "#22c55e",
  HGA: "#8b5cf6",
  "CP-SAT": "#3b82f6",
};

interface Props {
  data: CompareResponse;
  instance: InstanceOut;
}

export default function UtilizationChart({ data, instance }: Props) {
  const [algo, setAlgo] = useState<AlgoKey>("GA");
  const algos = (["baseline", "SA", "GA", "HGA", "CP-SAT"] as AlgoKey[]).filter((a) => data.results[a]);
  const roomCap = instance.resource_capacities.room ?? 1;
  const staffCap = instance.resource_capacities.staff ?? 1;

  // ── 시간대별 동시 사용량(step series) for selected algo ──
  const sched = data.results[algo]?.schedule;
  const makespan = sched?.makespan ?? 1;
  const series = useMemo(() => {
    if (!sched) return [] as { t: number; room: number; staff: number }[];
    const evs: { t: number; room: number; staff: number }[] = [];
    for (const a of Object.values(sched.assignments)) {
      const staff = instance.tasks[a.task_id]?.resources?.staff ?? 0;
      evs.push({ t: a.start, room: +1, staff: +staff });
      evs.push({ t: a.end, room: -1, staff: -staff });
    }
    evs.sort((x, y) => x.t - y.t);
    const out: { t: number; room: number; staff: number }[] = [];
    let room = 0,
      staff = 0,
      lastT = 0;
    for (const e of evs) {
      if (e.t !== lastT) {
        out.push({ t: lastT, room, staff });
        lastT = e.t;
      }
      room += e.room;
      staff += e.staff;
    }
    out.push({ t: lastT, room, staff });
    return out;
  }, [sched, instance]);

  // 평균 가동률(시간가중)
  const avgUtil = useMemo(() => {
    if (series.length < 2 || makespan <= 0) return { room: 0, staff: 0 };
    let rSum = 0,
      sSum = 0;
    for (let i = 0; i < series.length - 1; i++) {
      const dt = series[i + 1].t - series[i].t;
      rSum += (series[i].room / roomCap) * dt;
      sSum += (series[i].staff / staffCap) * dt;
    }
    return { room: (rSum / makespan) * 100, staff: (sSum / makespan) * 100 };
  }, [series, makespan, roomCap, staffCap]);

  // ── SVG 시간대별 차트 좌표 ──
  const W = 1040,
    H = 240,
    padL = 48,
    padR = 16,
    padT = 16,
    padB = 30;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const toX = (t: number) => padL + (t / Math.max(1, makespan)) * chartW;
  const toY = (pct: number) => padT + chartH - (Math.min(100, pct) / 100) * chartH;

  function stepPath(key: "room" | "staff", cap: number): string {
    if (series.length === 0) return "";
    let d = `M ${toX(0)} ${toY(0)}`;
    for (let i = 0; i < series.length; i++) {
      const x = toX(series[i].t);
      const y = toY((series[i][key] / cap) * 100);
      d += ` L ${x} ${toY(i === 0 ? 0 : (series[i - 1][key] / cap) * 100)} L ${x} ${y}`;
    }
    d += ` L ${toX(makespan)} ${toY((series[series.length - 1][key] / cap) * 100)}`;
    return d;
  }
  function stepArea(key: "room" | "staff", cap: number): string {
    const line = stepPath(key, cap);
    if (!line) return "";
    return `${line} L ${toX(makespan)} ${toY(0)} L ${toX(0)} ${toY(0)} Z`;
  }

  return (
    <section className="space-y-6">
      <h2 className="text-xl font-semibold">자원 가동률</h2>

      {/* ① 알고리즘별 가동률 막대 */}
      <div>
        <h3 className="text-base font-medium text-gray-600 mb-3">알고리즘별 평균 가동률</h3>
        <div className="space-y-3">
          {algos.map((a) => {
            const u = data.results[a].metrics.resource_utilization ?? {};
            const room = (u.room ?? 0) * 100;
            const staff = (u.staff ?? 0) * 100;
            return (
              <div key={a} className="flex items-center gap-3">
                <div className="w-24 text-sm font-medium" style={{ color: ALGO_COLORS[a] }}>
                  {ALGO_LABELS[a]}
                </div>
                <div className="flex-1 space-y-1.5">
                  <UtilBar label="수술실" pct={room} color="#2563eb" />
                  <UtilBar label="의료진" pct={staff} color="#16a34a" />
                </div>
              </div>
            );
          })}
        </div>
        <p className="text-xs text-gray-400 mt-2">
          가동률 = Σ(자원수요 × 소요시간) ÷ (용량 × 전체완료시각). 현장 권장 수술실 가동률은 50~60%대입니다.
        </p>
      </div>

      {/* ② 시간대별 가동률 곡선 */}
      <div>
        <div className="flex items-center gap-3 mb-2">
          <h3 className="text-base font-medium text-gray-600">시간대별 가동률</h3>
          <div className="flex gap-1.5">
            {algos.map((a) => (
              <button
                key={a}
                onClick={() => setAlgo(a)}
                className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${
                  algo === a ? "bg-blue-600 text-white" : "bg-white border text-gray-600 hover:bg-gray-50"
                }`}
              >
                {ALGO_LABELS[a]}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-4 mb-2 text-sm">
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: "#2563eb" }} />
            수술실 (평균 {avgUtil.room.toFixed(0)}%)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: "#16a34a" }} />
            의료진 (평균 {avgUtil.staff.toFixed(0)}%)
          </span>
        </div>
        <div className="overflow-x-auto">
          <svg width={W} height={H} style={{ minWidth: W }}>
            {/* y grid 0/50/100% */}
            {[0, 25, 50, 75, 100].map((p) => (
              <g key={p}>
                <line x1={padL} x2={W - padR} y1={toY(p)} y2={toY(p)} stroke="#e5e7eb" strokeWidth={1} />
                <text x={padL - 6} y={toY(p) + 4} textAnchor="end" fontSize={10} fill="#9ca3af">
                  {p}%
                </text>
              </g>
            ))}
            {/* 100% reference */}
            <line x1={padL} x2={W - padR} y1={toY(100)} y2={toY(100)} stroke="#fca5a5" strokeWidth={1} strokeDasharray="4 3" />
            {/* areas */}
            <path d={stepArea("staff", staffCap)} fill="#16a34a" opacity={0.18} />
            <path d={stepArea("room", roomCap)} fill="#2563eb" opacity={0.18} />
            <path d={stepPath("staff", staffCap)} fill="none" stroke="#16a34a" strokeWidth={1.8} />
            <path d={stepPath("room", roomCap)} fill="none" stroke="#2563eb" strokeWidth={1.8} />
            {/* x axis */}
            <line x1={padL} x2={W - padR} y1={toY(0)} y2={toY(0)} stroke="#9ca3af" strokeWidth={1} />
            {[0, 0.25, 0.5, 0.75, 1].map((f) => (
              <text key={f} x={toX(makespan * f)} y={H - 10} textAnchor="middle" fontSize={10} fill="#6b7280">
                {Math.round(makespan * f)}분
              </text>
            ))}
          </svg>
        </div>
        <p className="text-xs text-gray-400 mt-1">
          각 시점에 동시에 쓰이는 수술실·의료진 비율. 100%(빨간 점선)에 가까울수록 자원을 빈틈없이 활용 중입니다.
        </p>
      </div>
    </section>
  );
}

function UtilBar({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-12 text-xs text-gray-500">{label}</span>
      <div className="flex-1 h-5 bg-gray-100 rounded overflow-hidden relative">
        <div
          className="h-full rounded transition-[width] duration-300"
          style={{ width: `${Math.min(100, pct)}%`, background: color }}
        />
      </div>
      <span className="w-12 text-sm font-medium text-right" style={{ color }}>
        {pct.toFixed(0)}%
      </span>
    </div>
  );
}
