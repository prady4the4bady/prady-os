"""Directed Acyclic Graph for tracking subtask dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class DAGNode:
    subtask_id: str
    depends_on: List[str] = field(default_factory=list)
    # pending | running | completed | failed
    status: str = "pending"


class DAG:
    """In-process DAG for orchestrating subtask execution order."""

    def __init__(self) -> None:
        self._nodes: Dict[str, DAGNode] = {}

    def add_node(self, subtask_id: str, depends_on: List[str] | None = None) -> None:
        self._nodes[subtask_id] = DAGNode(subtask_id, depends_on or [])

    def mark_running(self, subtask_id: str) -> None:
        if subtask_id in self._nodes:
            self._nodes[subtask_id].status = "running"

    def mark_complete(self, subtask_id: str) -> None:
        if subtask_id in self._nodes:
            self._nodes[subtask_id].status = "completed"

    def mark_failed(self, subtask_id: str) -> None:
        if subtask_id in self._nodes:
            self._nodes[subtask_id].status = "failed"

    def ready_to_run(self) -> List[str]:
        """Return IDs of pending subtasks whose dependencies are all completed."""
        ready = []
        for node in self._nodes.values():
            if node.status != "pending":
                continue
            deps_done = all(
                self._nodes.get(dep, DAGNode(dep, status="completed")).status
                == "completed"
                for dep in node.depends_on
            )
            if deps_done:
                ready.append(node.subtask_id)
        return ready

    def is_complete(self) -> bool:
        """True when every node has reached a terminal state."""
        return bool(self._nodes) and all(
            n.status in ("completed", "failed") for n in self._nodes.values()
        )

    def has_failures(self) -> bool:
        return any(n.status == "failed" for n in self._nodes.values())

    def has_cycle(self) -> bool:
        """DFS-based cycle detection. Returns True if any cycle exists."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(nid: str) -> bool:
            visited.add(nid)
            rec_stack.add(nid)
            node = self._nodes.get(nid)
            if node:
                for dep in node.depends_on:
                    if dep in rec_stack:
                        return True
                    if dep not in visited and dfs(dep):
                        return True
            rec_stack.discard(nid)
            return False

        return any(nid not in visited and dfs(nid) for nid in self._nodes)

    def node_count(self) -> int:
        return len(self._nodes)

    def statuses(self) -> Dict[str, str]:
        return {nid: n.status for nid, n in self._nodes.items()}
