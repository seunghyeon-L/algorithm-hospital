// lib/api.ts — typed API client for the FastAPI backend

// 운영 환경(HF Spaces)에서는 프론트와 API가 같은 출처에서 서빙되므로 상대경로("")를 쓴다.
// 로컬 개발에서는 localhost:8000으로 폴백. 빌드 시 NEXT_PUBLIC_API_BASE로 덮어쓸 수 있다.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Request / Response types (mirrors backend Pydantic schemas)
// ---------------------------------------------------------------------------

export interface GenerateInstanceRequest {
  n_patients: number;
  seed: number;
  n_rooms: number;
  n_staff: number;
  n_anesthesia: number;
  n_pacu: number;
  n_emergency: number;
  turnover?: number;
}

export interface TaskOut {
  task_id: string;
  duration: number;
  resources: Record<string, number>;
  predecessors: string[];
  label: string | null;
  patient_id: string | null;
}

export interface InstanceOut {
  instance_id: string;
  n_tasks: number;
  resource_capacities: Record<string, number>;
  seed: number | null;
  source: string;
  turnover?: number;
  tasks: Record<string, TaskOut>;
}

export interface TaskAssignmentOut {
  task_id: string;
  start: number;
  end: number;
  room: string | null;
  wait: number;
  ready: number;
}

export interface ScheduleOut {
  instance_id: string;
  algo: string;
  wall_clock_sec: number;
  total_wait: number;
  makespan: number;
  assignments: Record<string, TaskAssignmentOut>;
}

export interface MetricsOut {
  instance_id: string;
  algo: string;
  total_wait: number;
  makespan: number;
  resource_utilization: Record<string, number>;
  wall_clock_sec: number;
  n_tasks: number;
  pct_improvement_vs_baseline: number | null;
}

export interface CriticalPathOut {
  length: number;
  task_ids: string[];
}

export interface AlgoResult {
  metrics: MetricsOut;
  schedule: ScheduleOut;
}

export interface CompareResponse {
  instance_id: string;
  critical_path: CriticalPathOut;
  results: Record<string, AlgoResult>;
  summary: Record<string, unknown>;
}

export interface CompareRequest {
  instance_id: string;
  time_limit_sec: number;
  random_seed: number;
  weighted: boolean;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function createInstance(req: GenerateInstanceRequest): Promise<InstanceOut> {
  const resp = await fetch(`${API_BASE}/instances`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`POST /instances failed (${resp.status}): ${err}`);
  }
  return resp.json();
}

export async function compareAlgos(req: CompareRequest): Promise<CompareResponse> {
  const resp = await fetch(`${API_BASE}/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`POST /compare failed (${resp.status}): ${err}`);
  }
  return resp.json();
}
