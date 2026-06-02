"use client";

// Pure-SVG DAG visualisation with critical-path highlighting.
// Nodes are laid out by topological level (x = level, y = position within level).
// Critical path nodes/edges are drawn in orange; others in gray.

import type { InstanceOut, CriticalPathOut } from "../lib/api";

interface Props {
  instance: InstanceOut;
  criticalPath: CriticalPathOut;
}

const NODE_W = 62;
const NODE_H = 28;
const H_GAP = 96;  // horizontal gap between levels
const V_GAP = 38;  // vertical gap between nodes in same level

function computeLevels(instance: InstanceOut): Map<string, number> {
  const levels = new Map<string, number>();
  const taskIds = Object.keys(instance.tasks);

  // BFS from roots
  const inDeg = new Map<string, number>();
  taskIds.forEach((id) => inDeg.set(id, instance.tasks[id].predecessors.length));
  const queue: string[] = taskIds.filter((id) => inDeg.get(id) === 0);
  queue.forEach((id) => levels.set(id, 0));

  while (queue.length > 0) {
    const curr = queue.shift()!;
    const lvl = levels.get(curr)!;
    // find successors
    for (const id of taskIds) {
      if (instance.tasks[id].predecessors.includes(curr)) {
        const newLvl = Math.max(levels.get(id) ?? 0, lvl + 1);
        levels.set(id, newLvl);
        const deg = (inDeg.get(id) ?? 1) - 1;
        inDeg.set(id, deg);
        if (deg === 0) queue.push(id);
      }
    }
  }
  return levels;
}

export default function DagGraph({ instance, criticalPath }: Props) {
  const cpSet = new Set(criticalPath.task_ids);
  // build cp edge set
  const cpEdges = new Set<string>();
  for (let i = 0; i < criticalPath.task_ids.length - 1; i++) {
    cpEdges.add(`${criticalPath.task_ids[i]}->${criticalPath.task_ids[i + 1]}`);
  }

  const levels = computeLevels(instance);
  const maxLevel = Math.max(...Array.from(levels.values()), 0);

  // group by level
  const byLevel = new Map<number, string[]>();
  for (const [id, lvl] of levels.entries()) {
    if (!byLevel.has(lvl)) byLevel.set(lvl, []);
    byLevel.get(lvl)!.push(id);
  }

  // Only render up to 12 levels wide / 10 nodes per level to keep SVG manageable
  const MAX_LEVELS = 18;
  const MAX_PER_LEVEL = 14;
  const visLevels = Math.min(maxLevel + 1, MAX_LEVELS);

  // node positions
  const pos = new Map<string, { x: number; y: number }>();
  for (let lvl = 0; lvl < visLevels; lvl++) {
    const nodes = (byLevel.get(lvl) ?? []).slice(0, MAX_PER_LEVEL);
    nodes.forEach((id, i) => {
      pos.set(id, {
        x: lvl * (NODE_W + H_GAP) + 8,
        y: i * (NODE_H + V_GAP) + 8,
      });
    });
  }

  const visNodes = Array.from(pos.keys());
  const visSet = new Set(visNodes);

  const svgW = visLevels * (NODE_W + H_GAP) + 16;
  const maxNodesInLevel = Math.max(
    ...Array.from({ length: visLevels }, (_, l) =>
      Math.min((byLevel.get(l) ?? []).length, MAX_PER_LEVEL)
    ),
    1
  );
  const svgH = maxNodesInLevel * (NODE_H + V_GAP) + 16;

  // edges
  const edges: { src: string; dst: string; isCp: boolean }[] = [];
  for (const id of visNodes) {
    for (const pred of instance.tasks[id]?.predecessors ?? []) {
      if (visSet.has(pred)) {
        edges.push({
          src: pred,
          dst: id,
          isCp: cpEdges.has(`${pred}->${id}`),
        });
      }
    }
  }

  return (
    <section>
      <h2 className="text-xl font-semibold mb-1">DAG + 임계경로</h2>
      <p className="text-xs text-gray-400 mb-2">
        주황색 = 임계경로 (자원 무시 이론적 하한, {criticalPath.length}분).
        {instance.n_tasks > visNodes.length
          ? ` 전체 ${instance.n_tasks}개 중 처음 ${visNodes.length}개 작업 표시.`
          : ""}
      </p>
      <div className="overflow-x-auto rounded border bg-white p-2">
        <svg width={svgW} height={svgH} style={{ minWidth: svgW, minHeight: svgH }}>
          {/* edges */}
          {edges.map(({ src, dst, isCp }) => {
            const s = pos.get(src)!;
            const d = pos.get(dst)!;
            const x1 = s.x + NODE_W;
            const y1 = s.y + NODE_H / 2;
            const x2 = d.x;
            const y2 = d.y + NODE_H / 2;
            const cx = (x1 + x2) / 2;
            return (
              <path
                key={`${src}->${dst}`}
                d={`M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`}
                stroke={isCp ? "#f97316" : "#d1d5db"}
                strokeWidth={isCp ? 2 : 1}
                fill="none"
                markerEnd={isCp ? "url(#arrowOrange)" : "url(#arrowGray)"}
              />
            );
          })}
          {/* nodes */}
          {visNodes.map((id) => {
            const p = pos.get(id)!;
            const isCp = cpSet.has(id);
            return (
              <g key={id}>
                <rect
                  x={p.x}
                  y={p.y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={4}
                  fill={isCp ? "#fff7ed" : "#f3f4f6"}
                  stroke={isCp ? "#f97316" : "#9ca3af"}
                  strokeWidth={isCp ? 2 : 1}
                />
                <text
                  x={p.x + NODE_W / 2}
                  y={p.y + NODE_H / 2 + 4}
                  textAnchor="middle"
                  fontSize={9}
                  fill={isCp ? "#c2410c" : "#374151"}
                  fontWeight={isCp ? "bold" : "normal"}
                >
                  {id}
                </text>
              </g>
            );
          })}
          {/* arrow markers */}
          <defs>
            <marker id="arrowGray" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#d1d5db" />
            </marker>
            <marker id="arrowOrange" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#f97316" />
            </marker>
          </defs>
        </svg>
      </div>
    </section>
  );
}
