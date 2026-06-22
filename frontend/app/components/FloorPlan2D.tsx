"use client";

// FloorPlan2D — 2D 평면도 동선 시뮬레이션.
// 수술실을 박스로, 의료진(스태프)을 점으로 표현한다. 선택한 알고리즘의 일정(schedule)을
// 시간축으로 재생하면, 각 시점의 활성 수술(start<=t<end)이 배정된 수술실이 점등되고
// 스태프 점이 대기실(pool)에서 해당 수술실로 이동(CSS transition)해 작업한 뒤
// 다음 수술실로 옮겨가는 모습을 가시화한다. 외부 라이브러리 없이 div+CSS로 구현.
// 보드는 컨테이너 전체 폭을 채우도록 반응형으로 크기를 계산한다.

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

// 전공과별 색상 — 수술실 외곽선·의료진(간호인력) 점·범례에 사용.
// 라벨("유리체절제술·PRECHECK")의 수술명(앞부분)으로 전공과를 판별한다.
// (백엔드 jnuh5.JNUH5_SURGERY_TYPES의 9개 과 + 응급과 동기화)
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
  emergency: { ko: "응급",       color: "#dc2626" },
};

const SURGERY_DEPT: Record<string, string> = {
  충수절제술: "surg_gs", 담낭절제술: "surg_gs", 탈장교정술: "surg_gs", 대장절제술: "surg_gs",
  슬관절치환술: "surg_os", 고관절치환술: "surg_os", 골절정복술: "surg_os",
  추간판절제술: "surg_ns", 개두술: "surg_ns",
  제왕절개: "surg_obgy", 자궁절제술: "surg_obgy",
  백내장수술: "surg_oph", 유리체절제술: "surg_oph",
  편도절제술: "surg_ent", 부비동내시경수술: "surg_ent",
  경요도절제술: "surg_uro", 요로결석제거술: "surg_uro",
  폐엽절제술: "surg_cs",
  피판재건술: "surg_ps",
  응급수술: "emergency",
};

const DEFAULT_DEPT_COLOR = "#64748b";
function deptOfLabel(label: string | null): string {
  if (!label) return "";
  const name = label.split("·")[0];
  return SURGERY_DEPT[name] ?? "";
}
function deptColor(dept: string): string {
  return DEPT_META[dept]?.color ?? DEFAULT_DEPT_COLOR;
}

interface ActiveTask {
  task_id: string;
  room: string;
  start: number;
  end: number;
  staff: number;
  label: string | null;
  dept: string;
}

interface Props {
  instance: InstanceOut;
  result: CompareResponse;
}

const GAP = 20;
const PAD = 20;
const ROOMS_PER_ROW = 5; // 한 줄 최대 수술실 수

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
  const staffCap = instance.resource_capacities.staff ?? 0;

  const rooms = useMemo(() => {
    const set = new Set<string>();
    const nRooms = instance.resource_capacities.room ?? 0;
    for (let i = 0; i < nRooms; i++) set.add(`room-${i + 1}`);
    if (schedule) {
      for (const a of Object.values(schedule.assignments)) {
        if (a.room) set.add(a.room);
      }
    }
    return Array.from(set).sort((a, b) => {
      const na = Number(a.replace(/\D/g, "")) || 0;
      const nb = Number(b.replace(/\D/g, "")) || 0;
      return na - nb;
    });
  }, [instance, schedule]);

  const tasks = useMemo<ActiveTask[]>(() => {
    if (!schedule) return [];
    // 5단계 모델에서 수술실을 점유하는 작업은 SURG뿐 — room이 배정된 작업만 평면도에 표시
    return Object.values(schedule.assignments)
      .filter((a) => !!a.room)
      .map((a) => ({
        task_id: a.task_id,
        room: a.room as string,
        start: a.start,
        end: a.end,
        staff: instance.tasks[a.task_id]?.resources?.staff ?? 0,
        label: instance.tasks[a.task_id]?.label ?? null,
        dept: deptOfLabel(instance.tasks[a.task_id]?.label ?? null),
      }));
  }, [schedule, instance]);

  // 현재 일정에 등장하는 전공과(범례용, DEPT_META 정의 순서)
  const deptsPresent = useMemo(() => {
    const set = new Set<string>();
    for (const task of tasks) if (task.dept) set.add(task.dept);
    return Object.keys(DEPT_META).filter((d) => set.has(d));
  }, [tasks]);

  // 과별 집도의(전공의) 정원 — resource_capacities의 surg_* 키(외과11·정형7…)
  const surgeonCaps = useMemo(() => {
    const caps: Record<string, number> = {};
    for (const [k, v] of Object.entries(instance.resource_capacities)) {
      if (k.startsWith("surg_") && v > 0) caps[k] = v;
    }
    return caps;
  }, [instance]);
  const surgeonDepts = useMemo(
    () => Object.keys(DEPT_META).filter((d) => (surgeonCaps[d] ?? 0) > 0),
    [surgeonCaps]
  );

  // 시각 t에 집도 중인 과별 집도의 수(활성 SURG가 소비하는 surg_* 자원; 응급은 외과 집도의)
  const surgeonsInUse = useMemo(() => {
    const m: Record<string, number> = {};
    if (!schedule) return m;
    for (const a of Object.values(schedule.assignments)) {
      if (a.start <= t && t < a.end) {
        const res = instance.tasks[a.task_id]?.resources ?? {};
        for (const k of Object.keys(res)) if (k.startsWith("surg_")) m[k] = (m[k] ?? 0) + 1;
      }
    }
    return m;
  }, [schedule, instance, t]);

  // ---- 반응형 치수 계산: 보드 폭을 채우도록 수술실 크기 산출 ----
  const perRow = Math.min(rooms.length, ROOMS_PER_ROW) || 1;
  const roomW = clamp((boardW - PAD * 2 - (perRow - 1) * GAP) / perRow, 220, 520);
  const roomH = clamp(Math.round(roomW * 0.62), 180, 300);
  const dot = clamp(Math.round(roomW / 11), 22, 34); // 의료진 점 지름
  const nRowsRoom = Math.ceil(rooms.length / perRow);
  const roomsAreaH = nRowsRoom * roomH + (nRowsRoom - 1) * GAP;
  const poolLabelY = PAD + roomsAreaH + GAP + 8;
  const poolY = poolLabelY + 26;
  const poolH = Math.max(96, dot * 2 + 44);
  const boardH = poolY + poolH + PAD;

  const roomRect = (room: string) => {
    const idx = rooms.indexOf(room);
    const r = Math.floor(idx / perRow);
    const c = idx % perRow;
    return {
      x: PAD + c * (roomW + GAP),
      y: PAD + r * (roomH + GAP),
      w: roomW,
      h: roomH,
    };
  };

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

  const activeByRoom = useMemo(() => {
    const m = new Map<string, ActiveTask>();
    for (const task of tasks) {
      if (task.start <= t && t < task.end) m.set(task.room, task);
    }
    return m;
  }, [tasks, t]);

  // 스태프 안정 배치(place)
  const placeRef = useRef<string[]>([]);
  if (placeRef.current.length !== staffCap) {
    placeRef.current = Array.from({ length: staffCap }, () => "pool");
  }
  const positions = useMemo(() => {
    const place = placeRef.current.slice();
    const need = new Map<string, number>();
    for (const [room, task] of activeByRoom) need.set(room, task.staff);

    const countInRoom = new Map<string, number>();
    for (let i = 0; i < staffCap; i++) {
      const p = place[i];
      if (p !== "pool" && need.has(p)) {
        const used = countInRoom.get(p) ?? 0;
        if (used < (need.get(p) ?? 0)) {
          countInRoom.set(p, used + 1);
          continue;
        }
      }
      place[i] = "pool";
    }
    for (const [room, demand] of need) {
      let have = countInRoom.get(room) ?? 0;
      for (let i = 0; i < staffCap && have < demand; i++) {
        if (place[i] === "pool") {
          place[i] = room;
          have++;
        }
      }
      countInRoom.set(room, have);
    }
    placeRef.current = place;

    const byPlace = new Map<string, number[]>();
    place.forEach((p, i) => {
      const arr = byPlace.get(p) ?? [];
      arr.push(i);
      byPlace.set(p, arr);
    });
    const pos: { left: number; top: number }[] = new Array(staffCap);
    const perRowRoom = Math.max(2, Math.floor((roomW - 24) / (dot + 8)));
    const perRowPool = Math.max(1, Math.floor((boardW - PAD * 2) / (dot + 10)));
    for (const [p, idxs] of byPlace) {
      idxs.forEach((staffIdx, slot) => {
        if (p === "pool") {
          const rr = Math.floor(slot / perRowPool);
          const cc = slot % perRowPool;
          pos[staffIdx] = {
            left: PAD + cc * (dot + 10),
            top: poolY + 30 + rr * (dot + 6),
          };
        } else {
          const rect = roomRect(p);
          const rr = Math.floor(slot / perRowRoom);
          const cc = slot % perRowRoom;
          pos[staffIdx] = {
            left: rect.x + 16 + cc * (dot + 8),
            top: rect.y + Math.round(roomH * 0.46) + rr * (dot + 6),
          };
        }
      });
    }
    return pos;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeByRoom, staffCap, rooms, roomW, roomH, dot, boardW, poolY]);

  if (!schedule) return null;

  const staffInUse = Array.from(activeByRoom.values()).reduce((s, x) => s + x.staff, 0);
  const activeCount = activeByRoom.size;
  const fmt = (x: number) => Math.round(x);

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-bold">2D 평면도 동선 시뮬레이션</h2>
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
          진행 수술: <b>{activeCount}</b>건
        </span>
        <span className="px-4 py-2 rounded-lg bg-green-50 text-green-700 border border-green-200">
          의료진 사용: <b>{staffInUse}</b> / {staffCap}명
        </span>
        <span className="px-4 py-2 rounded-lg bg-gray-50 text-gray-700 border">
          수술실: <b>{rooms.length}</b>개
        </span>
      </div>

      {/* 전공과 색상 범례 */}
      {deptsPresent.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm bg-white border rounded-xl px-4 py-3">
          <span className="font-semibold text-slate-600">전공과 색상:</span>
          {deptsPresent.map((d) => (
            <span key={d} className="inline-flex items-center gap-1.5">
              <span className="inline-block w-3.5 h-3.5 rounded-sm" style={{ background: deptColor(d) }} />
              <span className="text-slate-700">{DEPT_META[d].ko}</span>
            </span>
          ))}
          <span className="text-slate-400 sm:ml-auto">수술실 외곽선 · 의료진 점 = 해당 수술의 전공과</span>
        </div>
      )}

      {/* 평면도 보드 (전체 폭) */}
      <div ref={wrapRef} className="w-full">
        <div
          className="relative bg-slate-100 rounded-xl border overflow-hidden"
          style={{ width: "100%", height: boardH }}
        >
          {/* 수술실 박스 */}
          {rooms.map((room) => {
            const rect = roomRect(room);
            const task = activeByRoom.get(room);
            const busy = !!task;
            const dc = busy ? deptColor(task!.dept) : "#cbd5e1";
            const deptKo = busy ? (DEPT_META[task!.dept]?.ko ?? "수술중") : "대기";
            const progress = task ? (t - task.start) / Math.max(1, task.end - task.start) : 0;
            return (
              <div
                key={room}
                className="absolute rounded-xl border-2 transition-colors duration-300"
                style={{
                  left: rect.x,
                  top: rect.y,
                  width: rect.w,
                  height: rect.h,
                  background: busy ? "#ffffff" : "#f1f5f9",
                  borderColor: dc,
                  boxShadow: busy ? `0 0 0 4px ${dc}2e` : "none",
                }}
              >
                <div className="flex items-center justify-between px-3 pt-2">
                  <span className="text-base font-bold text-slate-700">🏥 {room}</span>
                  <span
                    className="text-sm px-2 py-0.5 rounded font-semibold"
                    style={{
                      background: busy ? `${dc}1f` : "#e2e8f0",
                      color: busy ? dc : "#64748b",
                    }}
                  >
                    {deptKo}
                  </span>
                </div>
                {task && (
                  <div className="px-3 mt-1">
                    <div className="text-sm text-slate-600 truncate">
                      {task.label ? task.label : task.task_id} · 👤 {task.staff}명
                    </div>
                    <div className="mt-1.5 h-2.5 bg-slate-200 rounded overflow-hidden">
                      <div
                        className="h-full transition-[width] duration-150"
                        style={{ width: `${Math.min(100, Math.max(0, progress * 100))}%`, background: dc }}
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {/* 대기실(pool) */}
          <div
            className="absolute text-base font-semibold text-slate-500"
            style={{ left: PAD, top: poolLabelY }}
          >
            🛋️ 간호인력 대기실
          </div>
          <div
            className="absolute rounded-xl border border-dashed border-slate-300 bg-white/40"
            style={{ left: PAD - 8, top: poolY, width: boardW - (PAD - 8) * 2, height: poolH }}
          />

          {/* 스태프 점 */}
          {Array.from({ length: staffCap }).map((_, i) => {
            const p = positions[i] ?? { left: PAD, top: poolY + 30 };
            const roomId = placeRef.current[i];
            const inRoom = roomId !== "pool";
            const sdept = inRoom ? activeByRoom.get(roomId)?.dept : undefined;
            const sc = sdept ? deptColor(sdept) : "#94a3b8";
            const sko = sdept ? DEPT_META[sdept]?.ko ?? "" : "";
            return (
              <div
                key={i}
                title={inRoom ? `간호인력 #${i + 1} · ${sko} 수술실` : `간호인력 #${i + 1} · 대기실`}
                className="absolute flex items-center justify-center rounded-full font-bold text-white"
                style={{
                  width: dot,
                  height: dot,
                  fontSize: Math.round(dot * 0.5),
                  left: p.left,
                  top: p.top,
                  background: sc,
                  boxShadow: inRoom ? `0 0 0 3px ${sc}40` : "none",
                  transition: "left 0.6s ease, top 0.6s ease, background 0.3s",
                  zIndex: 5,
                }}
              >
                👤
              </div>
            );
          })}
        </div>
      </div>

      {/* 과별 집도의(전공의) 가용 현황 */}
      {surgeonDepts.length > 0 && (
        <div className="bg-white border rounded-xl px-4 py-3 space-y-2.5">
          <div className="flex flex-wrap items-center gap-2 text-base font-semibold text-slate-700">
            🩺 과별 집도의(전공의) 가용 현황
            <span className="text-xs font-normal text-slate-400">
              진한 점 = 집도 중 · 옅은 점 = 대기 · 색 = 전공과
            </span>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-2.5">
            {surgeonDepts.map((d) => {
              const cap = surgeonCaps[d];
              const used = surgeonsInUse[d] ?? 0;
              const c = deptColor(d);
              return (
                <div key={d} className="flex items-center gap-1.5">
                  <span className="text-sm font-medium w-[68px]" style={{ color: c }}>
                    {DEPT_META[d]?.ko ?? d}
                  </span>
                  <span className="flex flex-wrap gap-1 max-w-[220px]">
                    {Array.from({ length: cap }).map((_, i) => (
                      <span
                        key={i}
                        className="inline-block w-3 h-3 rounded-full"
                        style={{
                          background: i < used ? c : "transparent",
                          border: `1.5px solid ${c}`,
                          opacity: i < used ? 1 : 0.35,
                          boxShadow: i < used ? `0 0 0 2px ${c}33` : "none",
                        }}
                      />
                    ))}
                  </span>
                  <span className="text-xs text-slate-500 font-mono">{used}/{cap}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <p className="text-sm text-gray-500">
        💡 수술실 외곽선·의료진(간호인력) 점 색은 <b>그 수술의 전공과</b>를 나타냅니다(응급=빨강).
        아래 <b>과별 집도의(전공의)</b> 패널은 과별 정원과 지금 집도 중인 인원을 색으로 보여줍니다.
        간호인력은 과 구분이 없는 공용 풀이라 대기 중엔 회색입니다.
        알고리즘을 바꿔가며 같은 인스턴스에서 동선·점유가 어떻게 달라지는지 비교해 보세요.
      </p>
    </section>
  );
}
