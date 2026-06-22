"use client";

// Pure-SVG grouped bar chart — no external chart library.
// Shows total_wait, makespan, and wall_clock_sec for baseline / rcpsp / ga.

import type { CompareResponse } from "../lib/api";

const ALGO_ORDER = ["baseline", "SA", "GA-seeded", "HGA", "CP-SAT"];
const ALGO_LABELS: Record<string, string> = {
  baseline: "베이스라인",
  SA: "SA",
  "GA-seeded": "GA-seeded",
  HGA: "HGA",
  "CP-SAT": "CP-SAT",
};
const ALGO_COLORS: Record<string, string> = {
  baseline: "#9ca3af",
  SA: "#f59e0b",
  "GA-seeded": "#22c55e",
  HGA: "#8b5cf6",
  "CP-SAT": "#3b82f6",
};

interface Props {
  data: CompareResponse;
}

function BarGroup({
  title,
  values,
  unit,
  width,
  height,
}: {
  title: string;
  values: { algo: string; value: number }[];
  unit: string;
  width: number;
  height: number;
}) {
  const maxVal = Math.max(...values.map((v) => v.value), 1);
  const padLeft = 60;
  const padRight = 20;
  const padTop = 20;
  const padBottom = 30;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;
  const barW = Math.floor(chartW / values.length) - 8;

  return (
    <div className="flex flex-col items-center">
      <div className="text-sm font-medium text-gray-600 mb-1">{title}</div>
      <svg width={width} height={height}>
        {/* y-axis grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
          const y = padTop + chartH * (1 - frac);
          const label = (maxVal * frac).toFixed(maxVal < 10 ? 2 : 0);
          return (
            <g key={frac}>
              <line
                x1={padLeft}
                x2={padLeft + chartW}
                y1={y}
                y2={y}
                stroke="#e5e7eb"
                strokeWidth={1}
              />
              <text x={padLeft - 4} y={y + 4} textAnchor="end" fontSize={9} fill="#9ca3af">
                {label}
              </text>
            </g>
          );
        })}
        {/* bars */}
        {values.map((v, i) => {
          const barH = (v.value / maxVal) * chartH;
          const x = padLeft + i * (chartW / values.length) + 4;
          const y = padTop + chartH - barH;
          return (
            <g key={v.algo}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={barH}
                fill={ALGO_COLORS[v.algo]}
                rx={3}
              />
              <text
                x={x + barW / 2}
                y={padTop + chartH + 16}
                textAnchor="middle"
                fontSize={10}
                fill="#374151"
              >
                {ALGO_LABELS[v.algo]}
              </text>
              <text
                x={x + barW / 2}
                y={y - 4}
                textAnchor="middle"
                fontSize={9}
                fill="#374151"
              >
                {maxVal < 10 ? v.value.toFixed(2) : v.value.toLocaleString()}
              </text>
            </g>
          );
        })}
        {/* axis */}
        <line
          x1={padLeft}
          x2={padLeft}
          y1={padTop}
          y2={padTop + chartH}
          stroke="#6b7280"
          strokeWidth={1}
        />
        <line
          x1={padLeft}
          x2={padLeft + chartW}
          y1={padTop + chartH}
          y2={padTop + chartH}
          stroke="#6b7280"
          strokeWidth={1}
        />
        {/* unit label */}
        <text x={8} y={padTop + chartH / 2} fontSize={9} fill="#9ca3af" transform={`rotate(-90,8,${padTop + chartH / 2})`} textAnchor="middle">
          {unit}
        </text>
      </svg>
    </div>
  );
}

export default function ComparisonChart({ data }: Props) {
  const algos = ALGO_ORDER.filter((a) => data.results[a]);

  const waitValues = algos.map((a) => ({
    algo: a,
    value: data.results[a].metrics.total_wait,
  }));
  const makespanValues = algos.map((a) => ({
    algo: a,
    value: data.results[a].metrics.makespan,
  }));
  const runtimeValues = algos.map((a) => ({
    algo: a,
    value: data.results[a].metrics.wall_clock_sec,
  }));

  return (
    <section>
      <h2 className="text-xl font-semibold mb-3">알고리즘 비교</h2>
      <div className="flex flex-wrap gap-6 justify-center">
        <BarGroup title="총 대기시간 (Σwait)" values={waitValues} unit="분" width={340} height={300} />
        <BarGroup title="완료시각 (makespan)" values={makespanValues} unit="분" width={340} height={300} />
        <BarGroup title="실행시간" values={runtimeValues} unit="초" width={340} height={300} />
      </div>
      {/* legend */}
      <div className="flex gap-4 justify-center mt-3">
        {algos.map((a) => (
          <div key={a} className="flex items-center gap-1 text-xs text-gray-600">
            <span
              className="inline-block w-3 h-3 rounded-sm"
              style={{ backgroundColor: ALGO_COLORS[a] }}
            />
            {ALGO_LABELS[a]}
          </div>
        ))}
      </div>
    </section>
  );
}
