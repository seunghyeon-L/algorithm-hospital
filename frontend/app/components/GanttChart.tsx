"use client";

// Pure-SVG Gantt chart — one row per room, one rect per task.
// Shows one algorithm's schedule at a time; caller renders one per algo.

import type { ScheduleOut } from "../lib/api";

const ROOM_COLORS = [
  "#bfdbfe", // blue-200
  "#bbf7d0", // green-200
  "#fde68a", // yellow-200
  "#fecaca", // red-200
  "#e9d5ff", // purple-200
  "#fed7aa", // orange-200
];

interface Props {
  schedule: ScheduleOut;
  title: string;
  accentColor: string;
}

export default function GanttChart({ schedule, title, accentColor }: Props) {
  // 수술실별 타임라인 — 실제 수술실을 점유하는 집도(SURG) 작업만 표시.
  // (PRECHECK·PREP·REC·DISCHARGE는 수술실 밖 단계라 방 라벨이 cosmetic임)
  const assignments = Object.values(schedule.assignments).filter((a) =>
    a.task_id.endsWith("_SURG")
  );
  if (assignments.length === 0) return null;

  // Collect unique rooms, sorted numerically (room-2 before room-10)
  const roomSet: string[] = [];
  for (const a of assignments) {
    const r = a.room ?? "room-1";
    if (!roomSet.includes(r)) roomSet.push(r);
  }
  roomSet.sort((a, b) => (Number(a.replace(/\D/g, "")) || 0) - (Number(b.replace(/\D/g, "")) || 0));

  const makespan = schedule.makespan;
  const rowH = 34;
  const padLeft = 72;
  const padRight = 24;
  const padTop = 24;
  const padBottom = 28;
  const svgW = 1120;
  const chartW = svgW - padLeft - padRight;
  const chartH = roomSet.length * rowH;
  const svgH = padTop + chartH + padBottom;

  const toX = (t: number) => padLeft + (t / makespan) * chartW;

  // x-axis ticks
  const nTicks = 6;
  const ticks = Array.from({ length: nTicks + 1 }, (_, i) =>
    Math.round((makespan / nTicks) * i)
  );

  return (
    <div className="overflow-x-auto">
      <div className="text-sm font-semibold mb-1" style={{ color: accentColor }}>
        {title}
      </div>
      <svg width={svgW} height={svgH} style={{ minWidth: svgW }}>
        {/* grid lines */}
        {ticks.map((t) => (
          <line
            key={t}
            x1={toX(t)}
            x2={toX(t)}
            y1={padTop}
            y2={padTop + chartH}
            stroke="#e5e7eb"
            strokeWidth={1}
          />
        ))}

        {/* room rows */}
        {roomSet.map((room, ri) => {
          const y = padTop + ri * rowH;
          const fill = ROOM_COLORS[ri % ROOM_COLORS.length];
          return (
            <g key={room}>
              {/* room label */}
              <text x={padLeft - 4} y={y + rowH / 2 + 4} textAnchor="end" fontSize={10} fill="#374151">
                {room}
              </text>
              {/* row background */}
              <rect x={padLeft} y={y} width={chartW} height={rowH} fill={ri % 2 === 0 ? "#f9fafb" : "#ffffff"} />
            </g>
          );
        })}

        {/* task bars */}
        {assignments.map((a) => {
          const room = a.room ?? "room-1";
          const ri = roomSet.indexOf(room);
          if (ri < 0) return null;
          const y = padTop + ri * rowH + 3;
          const x = toX(a.start);
          const w = Math.max(toX(a.end) - toX(a.start), 2);
          const fill = ROOM_COLORS[ri % ROOM_COLORS.length];
          return (
            <g key={a.task_id}>
              <rect x={x} y={y} width={w} height={rowH - 6} fill={fill} stroke={accentColor} strokeWidth={0.8} rx={2}>
                <title>{`${a.task_id}: start=${a.start} end=${a.end} wait=${a.wait}`}</title>
              </rect>
              {w > 20 && (
                <text x={x + 3} y={y + (rowH - 6) / 2 + 4} fontSize={8} fill="#1f2937" clipPath={`url(#clip-${a.task_id})`}>
                  {a.task_id}
                </text>
              )}
            </g>
          );
        })}

        {/* x-axis */}
        <line x1={padLeft} x2={padLeft + chartW} y1={padTop + chartH} y2={padTop + chartH} stroke="#9ca3af" strokeWidth={1} />
        {ticks.map((t) => (
          <text key={t} x={toX(t)} y={padTop + chartH + 14} textAnchor="middle" fontSize={9} fill="#6b7280">
            {t}
          </text>
        ))}
        <text x={padLeft + chartW / 2} y={padTop + chartH + 24} textAnchor="middle" fontSize={9} fill="#9ca3af">
          시간 (분)
        </text>
      </svg>
    </div>
  );
}
