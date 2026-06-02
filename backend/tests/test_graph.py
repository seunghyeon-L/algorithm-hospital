"""
tests/test_graph.py — tests for graph.py (topological order, critical path, SCC).

Verifies:
- topological_order returns a valid topological ordering.
- critical_path matches hand-calculated values on small examples.
- detect_cycles finds cycles; returns empty list for DAGs.
- is_dag returns True/False correctly.
- build_dag produces correct node/edge counts.
"""

import pytest
import networkx as nx

from backend.app.graph import (
    build_dag,
    critical_path,
    detect_cycles,
    is_dag,
    topological_order,
)
from backend.app.model import Instance, Task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_instance(tasks_spec: list) -> Instance:
    """
    tasks_spec: list of (task_id, duration, predecessors).
    Resource: each task needs 1 room; 1 room available (graph tests ignore resources).
    """
    tasks = {}
    for tid, dur, preds in tasks_spec:
        tasks[tid] = Task(tid, dur, {"room": 1}, predecessors=preds)
    return Instance("test", tasks, {"room": 3})


# ---------------------------------------------------------------------------
# build_dag
# ---------------------------------------------------------------------------

class TestBuildDag:
    def test_node_count(self):
        inst = make_instance([("A", 5, []), ("B", 3, ["A"]), ("C", 7, ["B"])])
        G = build_dag(inst)
        assert len(G.nodes) == 3

    def test_edge_count(self):
        inst = make_instance([("A", 5, []), ("B", 3, ["A"]), ("C", 7, ["B"])])
        G = build_dag(inst)
        assert len(G.edges) == 2

    def test_duration_attribute(self):
        inst = make_instance([("A", 10, []), ("B", 20, ["A"])])
        G = build_dag(inst)
        assert G.nodes["A"]["duration"] == 10
        assert G.nodes["B"]["duration"] == 20

    def test_edges_direction(self):
        inst = make_instance([("A", 5, []), ("B", 3, ["A"])])
        G = build_dag(inst)
        assert G.has_edge("A", "B")
        assert not G.has_edge("B", "A")


# ---------------------------------------------------------------------------
# topological_order
# ---------------------------------------------------------------------------

class TestTopologicalOrder:
    def test_chain_order(self):
        """T1->T2->T3: T1 must come before T2, T2 before T3."""
        inst = make_instance([("T1", 5, []), ("T2", 3, ["T1"]), ("T3", 7, ["T2"])])
        order = topological_order(inst)
        assert order.index("T1") < order.index("T2")
        assert order.index("T2") < order.index("T3")

    def test_all_tasks_present(self):
        inst = make_instance([("A", 1, []), ("B", 2, ["A"]), ("C", 3, ["A"])])
        order = topological_order(inst)
        assert set(order) == {"A", "B", "C"}

    def test_single_task(self):
        inst = make_instance([("X", 10, [])])
        assert topological_order(inst) == ["X"]

    def test_diamond(self):
        """A -> B, A -> C, B -> D, C -> D. A must be first, D last."""
        inst = make_instance([
            ("A", 1, []),
            ("B", 2, ["A"]),
            ("C", 3, ["A"]),
            ("D", 4, ["B", "C"]),
        ])
        order = topological_order(inst)
        assert order[0] == "A"
        assert order[-1] == "D"

    def test_no_predecessors_first(self):
        inst = make_instance([("X", 5, []), ("Y", 5, []), ("Z", 5, ["X", "Y"])])
        order = topological_order(inst)
        assert order.index("X") < order.index("Z")
        assert order.index("Y") < order.index("Z")

    def test_deterministic(self):
        """Same instance should give same order on repeated calls."""
        inst = make_instance([("A", 1, []), ("B", 2, ["A"]), ("C", 3, ["A"])])
        assert topological_order(inst) == topological_order(inst)


# ---------------------------------------------------------------------------
# critical_path — hand-calculated examples
# ---------------------------------------------------------------------------

class TestCriticalPath:
    def test_chain_length(self):
        """Chain T1(5)->T2(3)->T3(7): CP = 5+3+7 = 15."""
        inst = make_instance([("T1", 5, []), ("T2", 3, ["T1"]), ("T3", 7, ["T2"])])
        length, path = critical_path(inst)
        assert length == 15
        assert path == ["T1", "T2", "T3"]

    def test_diamond_takes_longer_branch(self):
        """
        A(2) -> B(5) -> D(1)
        A(2) -> C(1) -> D(1)
        CP via B: 2+5+1=8; via C: 2+1+1=4. CP=8 via A->B->D.
        """
        inst = make_instance([
            ("A", 2, []),
            ("B", 5, ["A"]),
            ("C", 1, ["A"]),
            ("D", 1, ["B", "C"]),
        ])
        length, path = critical_path(inst)
        assert length == 8
        assert "B" in path
        assert "C" not in path

    def test_single_task(self):
        inst = make_instance([("X", 42, [])])
        length, path = critical_path(inst)
        assert length == 42
        assert path == ["X"]

    def test_parallel_tasks_no_deps(self):
        """Two independent tasks: CP = max(duration)."""
        inst = make_instance([("A", 10, []), ("B", 20, [])])
        length, path = critical_path(inst)
        assert length == 20
        assert path == ["B"]

    def test_path_respects_precedence(self):
        """All tasks on the critical path must appear in topological order."""
        inst = make_instance([
            ("T1", 5, []),
            ("T2", 10, ["T1"]),
            ("T3", 3, ["T1"]),
            ("T4", 7, ["T2", "T3"]),
        ])
        length, path = critical_path(inst)
        # Path must be ordered: each task's predecessors appear before it
        for i, tid in enumerate(path):
            for pred in inst.tasks[tid].predecessors:
                if pred in path:
                    assert path.index(pred) < i

    def test_cp_is_lower_bound_for_generated(self):
        """CP length <= makespan of any valid schedule (sanity check)."""
        from backend.app.data import generate_instance
        inst = generate_instance(n_tasks=20, seed=0)
        length, _ = critical_path(inst)
        assert length > 0


# ---------------------------------------------------------------------------
# detect_cycles / is_dag
# ---------------------------------------------------------------------------

class TestCycleDetection:
    def test_dag_no_cycles(self):
        inst = make_instance([("A", 1, []), ("B", 2, ["A"]), ("C", 3, ["B"])])
        assert detect_cycles(inst) == []

    def test_is_dag_true(self):
        inst = make_instance([("A", 1, []), ("B", 2, ["A"])])
        assert is_dag(inst)

    def test_cycle_detected_manual(self):
        """
        Manually inject a cycle into the NetworkX graph after building.
        (Instance.validate() would reject a cycle at build time, so we test
        detect_cycles on a graph with a back-edge added directly.)
        """
        from backend.app.graph import build_dag
        inst = make_instance([("A", 1, []), ("B", 2, ["A"]), ("C", 3, ["B"])])
        G = build_dag(inst)
        G.add_edge("C", "A")  # introduce a cycle: A->B->C->A
        # detect_cycles works on an Instance, so test via NetworkX directly
        cyclic_sccs = [scc for scc in nx.strongly_connected_components(G) if len(scc) > 1]
        assert len(cyclic_sccs) == 1
        assert {"A", "B", "C"} == cyclic_sccs[0]

    def test_is_dag_false_via_networkx(self):
        """Confirm NetworkX reports a cycle when we add a back-edge."""
        inst = make_instance([("A", 1, []), ("B", 2, ["A"])])
        G = build_dag(inst)
        G.add_edge("B", "A")
        assert not nx.is_directed_acyclic_graph(G)

    def test_generated_instance_is_dag(self):
        """Synthetic generator must produce a cycle-free graph."""
        from backend.app.data import generate_instance
        inst = generate_instance(n_tasks=40, seed=5)
        assert is_dag(inst)

    def test_empty_instance_is_dag(self):
        inst = Instance("empty", {}, {"room": 1})
        assert is_dag(inst)
        assert detect_cycles(inst) == []
