"use client";

// FloorPlan2D — 환자 동선 시뮬레이션(구역형).
// 환자가 [수술 전 준비구역] → [수술실(집도)] → [회복실] → [퇴실] 4개 구역을 시간축에 따라
// 흐른다(PRECHECK∥PREP→SURG→REC→DISCHARGE). 각 환자는 현재 활성 단계가 속한 구역에 점으로
// 표시되고, 집도(SURG) 중에는 배정된 수술실 박스 안에 위치한다. 색은 환자의 전공과.
// 단계 사이 대기는 다음 구역에서 옅게 표시. 외부 라이브러리 없이 div+CSS로 구현하며,
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

// 전공과별 색상 — 수술실 외곽선·환자 점·집도의 패널·범례에 사용.
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

// ---------------------------------------------------------------------------
// 환자 단계/구역 모델
// ---------------------------------------------------------------------------
const STAGE_ORDER = ["PRECHECK", "PREP", "SURG", "REC", "DISCHARGE"];

interface PStage { start: number; end: number; room: string | null; }
interface PView { pid: string; dept: string; name: string; stages: Record<string, PStage>; }
type Zone = "arrival" | "prep" | "or" | "pacu" | "discharge" | "done";

const ZONE_KO: Record<string, string> = {
  prep: "수술 전 준비", or: "수술실(집도)", pacu: "회복실", discharge: "퇴실",
};

// 시각 t에서 환자의 위치(구역). PRECHECK∥PREP→SURG→REC→DISCHARGE 순서를 따른다.
// 단계가 끝나고 다음이 아직이면 "다음 구역에서 대기(active=false)"로 흐른다.
function locOf(pv: PView, t: number): { zone: Zone; room: string | null; active: boolean } {
  const started = STAGE_ORDER.filter((s) => pv.stages[s] && pv.stages[s].start <= t);
  if (started.length === 0) return { zone: "arrival", room: null, active: false };
  const F = started[started.length - 1];           // 가장 진행된(높은 순서) 단계
  const ft = pv.stages[F];
  if (F === "PRECHECK" || F === "PREP") {
    const active =
      (pv.stages["PRECHECK"] && t < pv.stages["PRECHECK"].end) ||
      (pv.stages["PREP"] && t < pv.stages["PREP"].end);
    return { zone: "prep", room: null, active: !!active };   // 준비 중 또는 수술실 대기
  }
  if (F === "SURG") {
    if (t < ft.end) return { zone: "or", room: ft.room, active: true };
    return { zone: "pacu", room: null, active: false };       // 집도 끝 → 회복실로 이동/대기
  }
  if (F === "REC") {
    if (t < ft.end) return { zone: "pacu", room: null, active: true };
    return { zone: "discharge", room: null, active: false };  // 회복 끝 → 퇴실 대기
  }
  if (t < ft.end) return { zone: "discharge", room: null, active: true };
  return { zone: "done", room: null, active: false };
}

interface Props {
  instance: InstanceOut;
  result: CompareResponse;
}

const PAD = 16;
const GAP = 14;

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

  // 수술실 목록 (집도 SURG만 점유; 정원 = resource_capacities.room)
  const rooms = useMemo(() => {
    const n = instance.resource_capacities.room ?? 0;
    return Array.from({ length: n }, (_, i) => `room-${i + 1}`);
  }, [instance]);

  // 환자별 5단계 일정
  const patients = useMemo<PView[]>(() => {
    if (!schedule) return [];
    const m = new Map<string, PView>();
    for (const a of Object.values(schedule.assignments)) {
      const tk = instance.tasks[a.task_id];
      if (!tk || !tk.patient_id) continue;
      const stage = a.task_id.split("_").pop() as string;
      let pv = m.get(tk.patient_id);
      if (!pv) {
        pv = { pid: tk.patient_id, dept: deptOfLabel(tk.label), name: (tk.label ?? "").split("·")[0], stages: {} };
        m.set(tk.patient_id, pv);
      }
      pv.stages[stage] = { start: a.start, end: a.end, room: a.room ?? null };
    }
    return [...m.values()].sort((a, b) => (a.pid < b.pid ? -1 : 1));
  }, [schedule, instance]);

  // 현재 일정에 등장하는 전공과(범례용, DEPT_META 정의 순서)
  const deptsPresent = useMemo(() => {
    const set = new Set<string>();
    for (const pv of patients) if (pv.dept) set.add(pv.dept);
    return Object.keys(DEPT_META).filter((d) => set.has(d));
  }, [patients]);

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

  // ---- 반응형 구역 레이아웃 계산 (세로 흐름: 준비→수술실→회복→퇴실) ----
  const perRoomRow = boardW < 760 ? 3 : boardW < 1120 ? 4 : 6;
  const nRoomRows = Math.max(1, Math.ceil(rooms.length / perRoomRow));
  const roomW = clamp((boardW - 2 * PAD - (perRoomRow - 1) * GAP) / perRoomRow, 150, 360);
  const roomH = clamp(Math.round(roomW * 0.5), 96, 150);
  const dot = clamp(Math.round(boardW / 58), 22, 30);
  const labelH = 24;
  const dotRowH = dot + 8;
  const stripContentH = 2 * dotRowH + 6;        // 환자 점 2줄

  const yPrepLabel = PAD;
  const yPrepContent = yPrepLabel + labelH;
  const prepZoneH = labelH + stripContentH;
  const yOrLabel = yPrepLabel + prepZoneH + GAP;
  const yOrContent = yOrLabel + labelH;
  const orContentH = nRoomRows * roomH + (nRoomRows - 1) * GAP;
  const orZoneH = labelH + orContentH;
  const yPacuLabel = yOrLabel + orZoneH + GAP;
  const yPacuContent = yPacuLabel + labelH;
  const pacuZoneH = labelH + stripContentH;
  const yDischLabel = yPacuLabel + pacuZoneH + GAP;
  const yDischContent = yDischLabel + labelH;
  const dischZoneH = labelH + stripContentH;
  const boardH = yDischLabel + dischZoneH + PAD;

  const roomIndex = useMemo(() => {
    const m = new Map<string, number>();
    rooms.forEach((r, i) => m.set(r, i));
    return m;
  }, [rooms]);
  const roomRect = (room: string) => {
    const i = roomIndex.get(room) ?? 0;
    const c = i % perRoomRow;
    const r = Math.floor(i / perRoomRow);
    return { x: PAD + c * (roomW + GAP), y: yOrContent + r * (roomH + GAP), w: roomW, h: roomH };
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

  // 시각 t의 환자 위치·수술실 점유 계산
  const layout = useMemo(() => {
    const stripPerRow = Math.max(1, Math.floor((boardW - 2 * PAD) / (dot + 8)));
    const slots: Record<string, number> = { prep: 0, pacu: 0, discharge: 0 };
    const dots: { pid: string; dept: string; left: number; top: number; zone: Zone; active: boolean }[] = [];
    const roomOcc = new Map<string, { pid: string; dept: string; name: string; stage: PStage }>();
    for (const pv of patients) {
      const loc = locOf(pv, t);
      if (loc.zone === "arrival" || loc.zone === "done") continue;
      if (loc.zone === "or" && loc.room) {
        roomOcc.set(loc.room, { pid: pv.pid, dept: pv.dept, name: pv.name, stage: pv.stages["SURG"] });
        const rect = roomRect(loc.room);
        dots.push({ pid: pv.pid, dept: pv.dept, zone: "or", active: true,
          left: rect.x + rect.w / 2 - dot / 2, top: rect.y + rect.h - dot - 6 });
      } else {
        const z = loc.zone as "prep" | "pacu" | "discharge";
        const slot = slots[z]++;
        const col = slot % stripPerRow;
        const row = Math.floor(slot / stripPerRow);
        const baseY = z === "prep" ? yPrepContent : z === "pacu" ? yPacuContent : yDischContent;
        dots.push({ pid: pv.pid, dept: pv.dept, zone: z, active: loc.active,
          left: PAD + col * (dot + 8), top: baseY + row * dotRowH });
      }
    }
    return { dots, roomOcc, counts: { prep: slots.prep, pacu: slots.pacu, discharge: slots.discharge, or: roomOcc.size } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patients, t, boardW, dot, roomW, roomH, perRoomRow, yPrepContent, yPacuContent, yDischContent, yOrContent]);

  if (!schedule) return null;

  const fmt = (x: number) => Math.round(x);
  const zones = [
    { key: "prep", y: yPrepLabel, h: prepZoneH, label: "🩺 수술 전 준비구역", sub: "확인·마취준비(PRECHECK∥PREP)", tint: "#eef2ff", count: layout.counts.prep },
    { key: "or", y: yOrLabel, h: orZoneH, label: "🏥 수술실 — 집도(SURG)", sub: `${rooms.length}실`, tint: "#f8fafc", count: layout.counts.or },
    { key: "pacu", y: yPacuLabel, h: pacuZoneH, label: "🛏 회복실 (PACU)", sub: "REC", tint: "#ecfdf5", count: layout.counts.pacu },
    { key: "discharge", y: yDischLabel, h: dischZoneH, label: "🚪 퇴실 구역", sub: "DISCHARGE", tint: "#fff7ed", count: layout.counts.discharge },
  ];

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-bold">환자 동선 시뮬레이션</h2>
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

      {/* 실시간 지표 (단계별 인원) */}
      <div className="flex flex-wrap gap-3 text-base">
        <span className="px-4 py-2 rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-200">
          준비 중: <b>{layout.counts.prep}</b>
        </span>
        <span className="px-4 py-2 rounded-lg bg-blue-50 text-blue-700 border border-blue-200">
          집도 중: <b>{layout.counts.or}</b> / {rooms.length}실
        </span>
        <span className="px-4 py-2 rounded-lg bg-green-50 text-green-700 border border-green-200">
          회복 중: <b>{layout.counts.pacu}</b>
        </span>
        <span className="px-4 py-2 rounded-lg bg-orange-50 text-orange-700 border border-orange-200">
          퇴실 중: <b>{layout.counts.discharge}</b>
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
          <span className="text-slate-400 sm:ml-auto">환자 점 · 수술실 외곽선 = 해당 환자의 전공과</span>
        </div>
      )}

      {/* 구역형 평면도 보드 (전체 폭) */}
      <div ref={wrapRef} className="w-full">
        <div
          className="relative bg-slate-100 rounded-xl border overflow-hidden"
          style={{ width: "100%", height: boardH }}
        >
          {/* 구역 배경 + 라벨 */}
          {zones.map((z) => (
            <div
              key={z.key}
              className="absolute rounded-lg border border-slate-200"
              style={{ left: PAD - 8, top: z.y - 2, width: boardW - (PAD - 8) * 2, height: z.h + 4, background: z.tint }}
            >
              <div className="px-2 pt-1 text-sm font-semibold text-slate-500">
                {z.label}{" "}
                <span className="text-xs font-normal text-slate-400">
                  {z.sub} · {z.count}명
                </span>
              </div>
            </div>
          ))}

          {/* 수술실 박스 (집도 SURG만 점등) */}
          {rooms.map((room) => {
            const occ = layout.roomOcc.get(room);
            const busy = !!occ;
            const rect = roomRect(room);
            const dc = busy ? deptColor(occ!.dept) : "#cbd5e1";
            const prog = busy ? clamp((t - occ!.stage.start) / Math.max(1, occ!.stage.end - occ!.stage.start), 0, 1) : 0;
            return (
              <div
                key={room}
                className="absolute rounded-lg border-2 transition-colors duration-300"
                style={{
                  left: rect.x,
                  top: rect.y,
                  width: rect.w,
                  height: rect.h,
                  background: busy ? "#ffffff" : "#f8fafc",
                  borderColor: dc,
                  boxShadow: busy ? `0 0 0 3px ${dc}2e` : "none",
                  zIndex: 1,
                }}
              >
                <div className="flex items-center justify-between px-2 pt-1">
                  <span className="text-xs font-bold text-slate-600">🏥 {room}</span>
                  {busy && (
                    <span
                      className="text-[11px] px-1.5 py-0.5 rounded font-semibold"
                      style={{ background: `${dc}1f`, color: dc }}
                    >
                      {DEPT_META[occ!.dept]?.ko ?? ""}
                    </span>
                  )}
                </div>
                {busy && (
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

          {/* 환자 점 (전공과 색 · 진한=처치 중, 옅은=대기/이동) */}
          {layout.dots.map((d) => {
            const c = deptColor(d.dept);
            return (
              <div
                key={d.pid}
                title={`${d.pid} · ${DEPT_META[d.dept]?.ko ?? ""} · ${ZONE_KO[d.zone] ?? d.zone}${d.active ? "" : " (대기)"}`}
                className="absolute flex items-center justify-center rounded-full text-white"
                style={{
                  width: dot,
                  height: dot,
                  fontSize: Math.round(dot * 0.46),
                  left: d.left,
                  top: d.top,
                  background: c,
                  opacity: d.active ? 1 : 0.5,
                  boxShadow: d.active ? `0 0 0 3px ${c}33` : "none",
                  transition: "left 0.6s ease, top 0.6s ease, opacity 0.3s, background 0.3s",
                  zIndex: 6,
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
        💡 환자가 <b>준비구역 → 수술실(집도) → 회복실 → 퇴실</b> 순서로 흐릅니다(색 = 전공과, 응급=빨강).
        수술실은 실제 집도(SURG) 중에만 점등되고, 환자는 단계 사이엔 다음 구역에서 옅게 대기합니다.
        아래 <b>과별 집도의(전공의)</b> 패널은 과별 정원과 지금 집도 중인 인원을 보여줍니다.
        알고리즘을 바꿔가며 같은 인스턴스에서 동선·점유가 어떻게 달라지는지 비교해 보세요.
      </p>
    </section>
  );
}
