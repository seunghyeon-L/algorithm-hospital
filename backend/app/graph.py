"""
graph.py — NetworkX graph utilities for the hospital scheduling DAG.

Provides:
  build_dag(instance)         — NetworkX DiGraph from an Instance
  topological_order(instance) — list of task_ids in topological order
  critical_path(instance)     — (length, path_task_ids)
                                 resource-free reference lower bound on makespan
  detect_cycles(instance)     — list of SCCs with >1 node (cycles = infeasible)
  is_dag(instance)            — True if no cycles

NOTE on critical_path:
  This is the DAG longest-path (precedence-only, resources IGNORED).
  It is a theoretical lower bound on makespan, NOT a feasible schedule.
  Labelled "reference lower bound" throughout — do NOT use as a baseline
  scheduler.  The baseline scheduler lives in baseline.py.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

import networkx as nx

try:
    from .model import Instance
except ImportError:
    from backend.app.model import Instance  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# DAG construction
# ---------------------------------------------------------------------------

def build_dag(instance: Instance) -> nx.DiGraph:
    """Build a NetworkX DiGraph from an Instance.

    Nodes carry 'duration' attribute; edges carry 'weight'=0 (the edge weight
    for longest-path is set on nodes, not edges, consistent with the standard
    node-weight CPM formulation).

    Args:
        instance: A validated Instance.

    Returns:
        nx.DiGraph with one node per task and directed edges for precedences.
    """
    G = nx.DiGraph()
    for task in instance.task_list():
        G.add_node(task.task_id, duration=task.duration, label=task.label or task.task_id)
    for src, dst in instance.edges():
        G.add_edge(src, dst)
    return G


# ---------------------------------------------------------------------------
# Topological ordering
# ---------------------------------------------------------------------------

def topological_order(instance: Instance) -> List[str]:
    """Return task_ids in a valid topological order.

    Uses NetworkX's lexicographical topological sort for determinism
    across runs (ties broken by node key string order).

    Args:
        instance: A validated Instance (assumed to be a DAG).

    Returns:
        List of task_ids such that all predecessors appear before successors.

    Raises:
        nx.NetworkXUnfeasible: If the graph contains a cycle.
    """
    G = build_dag(instance)
    return list(nx.lexicographical_topological_sort(G))


# ---------------------------------------------------------------------------
# Critical path (DAG longest path — resource-free reference lower bound)
# ---------------------------------------------------------------------------

def critical_path(instance: Instance) -> Tuple[int, List[str]]:
    """Compute the DAG longest path weighted by task durations.

    This is the standard Critical Path Method (CPM) applied to the precedence
    graph with edge weights = duration of the SOURCE node.  Resources are
    IGNORED — the result is a lower bound on makespan, not a feasible schedule.

    Algorithm: single-source longest path via dynamic programming in
    topological order (O(V + E)).

    Args:
        instance: A validated Instance (must be a DAG).

    Returns:
        (cp_length, cp_task_ids) where:
          cp_length    — integer, sum of durations along the critical path.
          cp_task_ids  — list of task_ids on the critical path (in order).

    Raises:
        nx.NetworkXUnfeasible: If the graph contains a cycle.
    """
    G = build_dag(instance)
    topo = list(nx.lexicographical_topological_sort(G))

    # dist[v] = longest path length (in minutes) ending at v (inclusive)
    dist: Dict[str, int] = {}
    prev: Dict[str, str | None] = {}

    for v in topo:
        dur = G.nodes[v]["duration"]
        best_pred_dist = max(
            (dist[u] for u in G.predecessors(v)), default=0
        )
        dist[v] = best_pred_dist + dur
        # Track which predecessor gave the best distance
        best_pred: str | None = None
        for u in G.predecessors(v):
            if dist[u] == best_pred_dist:
                best_pred = u
                break
        prev[v] = best_pred

    # Find the sink with maximum dist
    cp_end = max(topo, key=lambda v: dist[v])
    cp_length = dist[cp_end]

    # Reconstruct path by walking back through prev
    path: List[str] = []
    node: str | None = cp_end
    while node is not None:
        path.append(node)
        node = prev[node]
    path.reverse()

    return cp_length, path


# ---------------------------------------------------------------------------
# Cycle / SCC detection
# ---------------------------------------------------------------------------

def detect_cycles(instance: Instance) -> List[Set[str]]:
    """Detect cycles in the precedence graph using Tarjan's SCC algorithm.

    Returns all strongly-connected components with more than one node
    (i.e. actual cycles).  An empty list means the graph is a valid DAG.

    Args:
        instance: An Instance (may or may not be a DAG).

    Returns:
        List of sets, each set being the task_ids in one cyclic SCC.
        Empty list if the graph is acyclic.
    """
    G = build_dag(instance)
    cyclic_sccs: List[Set[str]] = []
    for scc in nx.strongly_connected_components(G):
        if len(scc) > 1:
            cyclic_sccs.append(scc)
        else:
            # A single-node SCC is a cycle only if there is a self-loop
            (node,) = scc
            if G.has_edge(node, node):
                cyclic_sccs.append(scc)
    return cyclic_sccs


def is_dag(instance: Instance) -> bool:
    """Return True if the instance's precedence graph is a DAG (no cycles)."""
    return len(detect_cycles(instance)) == 0
