"use client";

// FloorPlan2D — 집도의(전공의) 자원배분 시뮬레이션.
// 과별로 정원이 정해진 제약 자원인 집도의가, 일정에 따라 [과별 대기 벤치] ↔ [수술실]을
// 오간다. 수술이 시작되면 해당 과의 빈 집도의 1명이 수술실로 이동(CSS transition)하고,
// 끝나면 자기 벤치 자리로 돌아온다. 색은 전공과. 이로써 "한정된 과별 집도의를 동시
// 수술들에 어떻게 배분하는가"(자원 분배)를 시각적으로 보여준다. div+CSS만으로 구현.

import { useEffect, useMemo, useRef, useState } from "react";
import type { CompareResponse, InstanceOut } from "../lib/api";

type AlgoKey = "baseline" | "SA" | "GA-seeded" | "HGA" | "CP-SAT";

const ALGO_LABELS: Record<AlgoKey, string> = {
  baseline: "베이스라인",
  SA: "SA",
  "GA-seeded": "GA-seeded",
  HGA: "HGA",
  "CP-SAT": "CP-SAT",
};

// 전공과별 색상 — 집도의 점·수술실 외곽선·범례에 사용.
const DEPT_META: Record<string, { ko: string; color: string }> = {
  surg_gs:   { ko: "외과",       color: "#2563eb" },
  surg_os:   { ko: "정형외과",   color: "#16a34a" },
  surg_ns:   { ko: "신경외과",   color: "#7c3aed" },
  surg_obgy: { ko: "산부인과",   color: "#db2777" },
  surg_oph:  { ko: "안과",       color: "#0891b2" },
  surg_ent:  { ko: "이비인후과", color: "#d97706" },
  surg_uro:  { ko: "비뇨의학과", color: "#0d9488" },
  surg_cs:   { ko: "흉부외과",   color: "#4f46e5" },
  surg_ps:   { ko: "성형외과",   color: "#c026d3" },
};

const DEFAULT_DEPT_COLOR = "#64748b";
function deptColor(dept: string): string {
  return DEPT_META[dept]?.color ?? DEFAULT_DEPT_COLOR;
}

interface SurgAssign {
  dept: string;       // surg_* (응급은 surg_gs 소비)
  slot: number;       // 과 내 집도의 번호(고정 신원)
  start: number;
  end: number;
  room: string | null;
  name: string;       // 수술명(응급수술 등)
  emergency: boolean;
}

interface Props {
  instance: InstanceOut;
  result: CompareResponse;
}

const PAD = 16;
const GAP = 14;
const DEPT_LABEL_W = 88;

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

export default function FloorPlan2D({ instance, result }: Props) {
  const [algo, setAlgo] = useState<AlgoKey>("HGA");
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(40); // 분/초 (재생 배속)

  // 컨테이너 폭 측정 → 보드를 전체 폭으로 채움
  const wrapRef = useRef<HTMLDivElement>(null);
  const [boardW, setBoardW] = useState(1200);
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setBoardW(w);
    });
    ro.observe(el);
    setBoardW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const schedule = result.results[algo]?.schedule;
  const makespan = schedule?.makespan ?? 0;

  const rooms = useMemo(() => {
    const n = instance.resource_capacities.room ?? 0;
    return Array.from({ length: n }, (_, i) => `room-${i + 1}`);
  }, [instance]);

  // 과별 집도의 정원 (resource_capacities의 surg_* 키)
  const surgeonCaps = useMemo(() => {
    const caps: Record<string, number> = {};
    for (const [k, v] of Object.entries(instance.resource_capacities)) {
      if (k.startsWith("surg_") && v > 0) caps[k] = v;
    }
    return caps;
  }, [instance]);

  // 각 SURG를 과별 집도의 슬롯(고정 신원)에 배정 — 구간 그래프 색칠(정원=색 수, 동시 ≤ 정원)
  const surgAssign = useMemo(() => {
    const m = new Map<string, SurgAssign>();
    if (!schedule) return m;
    const byDept: Record<string, { tid: string; start: number; end: number; room: string | null; name: string; emergency: boolean }[]> = {};
    for (const a of Object.values(schedule.assignments)) {
      if (!a.task_id.endsWith("_SURG")) continue;
      const res = instance.tasks[a.task_id]?.resources ?? {};
      const dept = Object.keys(res).find((k) => k.startsWith("surg_"));
      if (!dept) continue;
      const name = (instance.tasks[a.task_id]?.label ?? "").split("·")[0];
      (byDept[dept] ??= []).push({ tid: a.task_id, start: a.start, end: a.end, room: a.room ?? null, name, emergency: a.task_id.startsWith("E") });
    }
    for (const dept of Object.keys(byDept)) {
      const cap = surgeonCaps[dept] ?? 1;
      const freeAt = new Array(cap).fill(-1);
      for (const s of byDept[dept].sort((x, y) => x.start - y.start)) {
        let pick = -1;
        for (let i = 0; i < cap; i++) if (freeAt[i] <= s.start) { pick = i; break; }
        if (pick < 0) { pick = 0; for (let i = 1; i < cap; i++) if (freeAt[i] < freeAt[pick]) pick = i; }
        freeAt[pick] = s.end;
        m.set(s.tid, { dept, slot: pick, start: s.start, end: s.end, room: s.room, name: s.name, emergency: s.emergency });
      }
    }
    return m;
  }, [schedule, instance, surgeonCaps]);

  // 벤치에 표시할 과(수술이 있는 과) — DEPT_META 순서
  const benchDepts = useMemo(() => {
    const set = new Set<string>();
    for (const a of surgAssign.values()) set.add(a.dept);
    return Object.keys(DEPT_META).filter((d) => set.has(d) && (surgeonCaps[d] ?? 0) > 0);
  }, [surgAssign, surgeonCaps]);

  // 시각 t: 집도 중인 집도의(과#슬롯) → 배정 / 수술실 점유
  const { busy, roomMap } = useMemo(() => {
    const busy = new Map<string, SurgAssign>();
    const roomMap = new Map<string, SurgAssign>();
    for (const a of surgAssign.values()) {
      if (a.start <= t && t < a.end) {
        busy.set(`${a.dept}#${a.slot}`, a);
        if (a.room) roomMap.set(a.room, a);
      }
    }
    return { busy, roomMap };
  }, [surgAssign, t]);

  // ---- 레이아웃: 위=수술실 그리드, 아래=과별 집도의 벤치 ----
  const perRoomRow = boardW < 760 ? 3 : boardW < 1120 ? 4 : 6;
  const nRoomRows = Math.max(1, Math.ceil(rooms.length / perRoomRow));
  const roomW = clamp((boardW - 2 * PAD - (perRoomRow - 1) * GAP) / perRoomRow, 150, 360);
  const roomH = clamp(Math.round(roomW * 0.5), 92, 140);
  const sDot = clamp(Math.round(boardW / 74), 18, 26);
  const labelH = 24;
  const benchRowH = sDot + 12;

  const yRoomsLabel = PAD;
  const yRoomsContent = yRoomsLabel + labelH;
  const roomsH = nRoomRows * roomH + (nRoomRows - 1) * GAP;
  const yWaitLabel = yRoomsContent + roomsH + GAP;
  const yWaitContent = yWaitLabel + labelH + 2;
  const waitH = Math.max(1, benchDepts.length) * benchRowH;
  const boardH = yWaitContent + waitH + PAD;

  const roomIndex = useMemo(() => {
    const m = new Map<string, number>();
    rooms.forEach((r, i) => m.set(r, i));
    return m;
  }, [rooms]);
  const roomRect = (room: string) => {
    const i = roomIndex.get(room) ?? 0;
    const c = i % perRoomRow;
    const r = Math.floor(i / perRoomRow);
    return { x: PAD + c * (roomW + GAP), y: yRoomsContent + r * (roomH + GAP), w: roomW, h: roomH };
  };
  const deptRow = useMemo(() => {
    const m = new Map<string, number>();
    benchDepts.forEach((d, i) => m.set(d, i));
    return m;
  }, [benchDepts]);

  // 집도의 점 위치: 집도 중이면 수술실, 아니면 자기 벤치 슬롯(고정)
  const surgeonDots = useMemo(() => {
    const dots: { key: string; dept: string; busy: boolean; left: number; top: number }[] = [];
    for (const dept of benchDepts) {
      const cap = surgeonCaps[dept] ?? 0;
      const row = deptRow.get(dept) ?? 0;
      for (let i = 0; i < cap; i++) {
        const key = `${dept}#${i}`;
        const b = busy.get(key);
        let left: number, top: number;
        if (b && b.room) {
          const rect = roomRect(b.room);
          left = rect.x + rect.w / 2 - sDot / 2;
          top = rect.y + rect.h - sDot - 7;
        } else {
          left = PAD + DEPT_LABEL_W + i * (sDot + 6);
          top = yWaitContent + row * benchRowH + (benchRowH - sDot) / 2;
        }
        dots.push({ key, dept, busy: !!b, left, top });
      }
    }
    return dots;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [benchDepts, busy, surgeonCaps, deptRow, boardW, roomW, roomH, perRoomRow, sDot, yWaitContent, yRoomsContent]);

  useEffect(() => {
    setT(0);
    setPlaying(false);
  }, [algo]);

  // 재생 루프
  const rafRef = useRef<number | null>(null);
  const lastRef = useRef<number | null>(null);
  useEffect(() => {
    if (!playing) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      lastRef.current = null;
      return;
    }
    const tick = (now: number) => {
      if (lastRef.current == null) lastRef.current = now;
      const dt = (now - lastRef.current) / 1000;
      lastRef.current = now;
      setT((prev) => {
        const next = prev + dt * speed;
        if (next >= makespan) {
          setPlaying(false);
          return makespan;
        }
        return next;
      });
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, speed, makespan]);

  if (!schedule) return null;

  const fmt = (x: number) => Math.round(x);
  const totalSurgeons = benchDepts.reduce((s, d) => s + (surgeonCaps[d] ?? 0), 0);
  const busyCount = busy.size;

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-bold">집도의(전공의) 자원배분 시뮬레이션</h2>
        <div className="flex gap-1.5">
          {(["baseline", "SA", "GA-seeded", "HGA", "CP-SAT"] as AlgoKey[]).map((a) => (
            <button
              key={a}
              onClick={() => setAlgo(a)}
              className={`px-4 py-2 rounded-lg text-base font-medium transition-colors ${
                algo === a ? "bg-blue-600 text-white" : "bg-white border text-gray-600 hover:bg-gray-50"
              }`}
            >
              {ALGO_LABELS[a]}
            </button>
          ))}
        </div>
      </div>

      {/* 컨트롤 */}
      <div className="flex flex-wrap items-center gap-4 bg-gray-50 border rounded-xl p-4">
        <button
          onClick={() => {
            if (t >= makespan) setT(0);
            setPlaying((p) => !p);
          }}
          className="px-5 py-2.5 bg-blue-600 text-white rounded-lg text-base font-semibold hover:bg-blue-700"
        >
          {playing ? "⏸ 일시정지" : t >= makespan ? "↻ 처음부터" : "▶ 재생"}
        </button>
        <button
          onClick={() => {
            setPlaying(false);
            setT(0);
          }}
          className="px-4 py-2.5 bg-white border rounded-lg text-base hover:bg-gray-100"
        >
          ⟲ 리셋
        </button>
        <label className="text-base text-gray-700 flex items-center gap-2">
          속도
          <input type="range" min={5} max={150} value={speed} onChange={(e) => setSpeed(Number(e.target.value))} />
          <span className="font-mono text-sm w-20">{speed}분/초</span>
        </label>
        <label className="text-base text-gray-700 flex items-center gap-2 flex-1 min-w-[260px]">
          시간
          <input
            type="range"
            min={0}
            max={makespan}
            value={t}
            onChange={(e) => {
              setPlaying(false);
              setT(Number(e.target.value));
            }}
            className="flex-1"
          />
          <span className="font-mono text-sm w-28">
            {fmt(t)} / {makespan}분
          </span>
        </label>
      </div>

      {/* 실시간 지표 */}
      <div className="flex flex-wrap gap-3 text-base">
        <span className="px-4 py-2 rounded-lg bg-blue-50 text-blue-700 border border-blue-200">
          집도 중 집도의: <b>{busyCount}</b> / {totalSurgeons}명
        </span>
        <span className="px-4 py-2 rounded-lg bg-gray-50 text-gray-700 border">
          사용 수술실: <b>{roomMap.size}</b> / {rooms.length}실
        </span>
        <span className="px-4 py-2 rounded-lg bg-green-50 text-green-700 border border-green-200">
          대기 집도의: <b>{totalSurgeons - busyCount}</b>명
        </span>
      </div>

      {/* 전공과 색상 범례 */}
      {benchDepts.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm bg-white border rounded-xl px-4 py-3">
          <span className="font-semibold text-slate-600">전공과 색상:</span>
          {benchDepts.map((d) => (
            <span key={d} className="inline-flex items-center gap-1.5">
              <span className="inline-block w-3.5 h-3.5 rounded-full" style={{ background: deptColor(d) }} />
              <span className="text-slate-700">{DEPT_META[d].ko}</span>
            </span>
          ))}
          <span className="text-slate-400 sm:ml-auto">집도의 점 = 전공과 · 진하면 수술실로 이동(집도 중)</span>
        </div>
      )}

      {/* 보드: 수술실 ↔ 집도의 벤치 */}
      <div ref={wrapRef} className="w-full">
        <div className="relative bg-slate-100 rounded-xl border overflow-hidden" style={{ width: "100%", height: boardH }}>
          {/* 구역 배경 + 라벨 */}
          <div
            className="absolute rounded-lg border border-slate-200"
            style={{ left: PAD - 8, top: yRoomsLabel - 2, width: boardW - (PAD - 8) * 2, height: labelH + roomsH + 8, background: "#f8fafc" }}
          >
            <div className="px-2 pt-1 text-sm font-semibold text-slate-500">
              🏥 수술실 — 집도(SURG){" "}
              <span className="text-xs font-normal text-slate-400">{rooms.length}실 · 사용 {roomMap.size}</span>
            </div>
          </div>
          <div
            className="absolute rounded-lg border border-slate-200"
            style={{ left: PAD - 8, top: yWaitLabel - 2, width: boardW - (PAD - 8) * 2, height: labelH + waitH + 6, background: "#eef2ff" }}
          >
            <div className="px-2 pt-1 text-sm font-semibold text-slate-500">
              🩺 집도의(전공의) 대기 벤치 — 과별{" "}
              <span className="text-xs font-normal text-slate-400">대기 {totalSurgeons - busyCount} · 집도 중 {busyCount}</span>
            </div>
          </div>

          {/* 벤치 과별 라벨 + 정원 카운트 */}
          {benchDepts.map((d) => {
            const row = deptRow.get(d) ?? 0;
            const cap = surgeonCaps[d] ?? 0;
            const used = benchDepts.length ? [...busy.values()].filter((b) => b.dept === d).length : 0;
            return (
              <div
                key={`lbl-${d}`}
                className="absolute text-xs font-semibold flex items-center"
                style={{ left: PAD, top: yWaitContent + row * benchRowH, width: DEPT_LABEL_W - 6, height: sDot, color: deptColor(d) }}
              >
                {DEPT_META[d]?.ko}
                <span className="ml-1 text-[10px] font-normal text-slate-400">{used}/{cap}</span>
              </div>
            );
          })}

          {/* 수술실 박스 */}
          {rooms.map((room) => {
            const occ = roomMap.get(room);
            const busyR = !!occ;
            const rect = roomRect(room);
            const dc = busyR ? deptColor(occ!.dept) : "#cbd5e1";
            const prog = busyR ? clamp((t - occ!.start) / Math.max(1, occ!.end - occ!.start), 0, 1) : 0;
            return (
              <div
                key={room}
                className="absolute rounded-lg border-2 transition-colors duration-300"
                style={{
                  left: rect.x, top: rect.y, width: rect.w, height: rect.h,
                  background: busyR ? "#ffffff" : "#f8fafc",
                  borderColor: dc,
                  boxShadow: busyR ? `0 0 0 3px ${dc}2e` : "none",
                  zIndex: 1,
                }}
              >
                <div className="flex items-center justify-between px-2 pt-1">
                  <span className="text-xs font-bold text-slate-600">🏥 {room}</span>
                  {busyR && (
                    <span className="text-[11px] px-1.5 py-0.5 rounded font-semibold" style={{ background: `${dc}1f`, color: dc }}>
                      {occ!.emergency ? "응급" : DEPT_META[occ!.dept]?.ko ?? ""}
                    </span>
                  )}
                </div>
                {busyR && (
                  <div className="px-2 mt-0.5">
                    <div className="text-[11px] text-slate-500 truncate">{occ!.name}</div>
                    <div className="mt-1 h-1.5 bg-slate-200 rounded overflow-hidden">
                      <div className="h-full transition-[width] duration-150" style={{ width: `${prog * 100}%`, background: dc }} />
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {/* 집도의 점 (벤치 ↔ 수술실 이동) */}
          {surgeonDots.map((s) => {
            const c = deptColor(s.dept);
            return (
              <div
                key={s.key}
                title={`${DEPT_META[s.dept]?.ko ?? ""} 집도의 ${s.key.split("#")[1]}번 · ${s.busy ? "집도 중" : "대기"}`}
                className="absolute rounded-full"
                style={{
                  width: sDot, height: sDot,
                  left: s.left, top: s.top,
                  background: s.busy ? c : "#ffffff",
                  border: `2px solid ${c}`,
                  boxShadow: s.busy ? `0 0 0 3px ${c}40` : "none",
                  transition: "left 0.6s ease, top 0.6s ease, background 0.3s",
                  zIndex: 6,
                }}
              />
            );
          })}
        </div>
      </div>

      <p className="text-sm text-gray-500">
        💡 점은 <b>집도의(전공의)</b>입니다(색 = 전공과). 수술이 시작되면 해당 과의 빈 집도의 1명이
        <b> 벤치에서 수술실로 이동</b>(채워진 점)하고, 끝나면 자기 자리로 돌아옵니다.
        과별 정원은 한정돼 있어, 같은 과 수술이 몰리면 그 과 벤치가 비고 — 한정된 집도의를 동시
        수술들에 어떻게 <b>배분</b>하는지(자원 분배)를 알고리즘별로 비교해 보세요.
      </p>
    </section>
  );
}
