from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from time import perf_counter
from typing import Any

from app.schemas import AgentTraceStep


State = dict[str, Any]
Node = tuple[str, Callable[[State], State]]


class TraceRecorder:
    def __init__(self) -> None:
        self.steps: list[AgentTraceStep] = []

    def run(self, name: str, input_summary: dict[str, Any], action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        started_at = datetime.utcnow()
        start = perf_counter()
        try:
            output_summary = action()
            self.steps.append(
                AgentTraceStep(
                    name=name,
                    status="success",
                    started_at=started_at,
                    duration_ms=round((perf_counter() - start) * 1000),
                    input_summary=_compact(input_summary),
                    output_summary=_compact(output_summary),
                )
            )
            return output_summary
        except Exception as exc:
            self.steps.append(
                AgentTraceStep(
                    name=name,
                    status="error",
                    started_at=started_at,
                    duration_ms=round((perf_counter() - start) * 1000),
                    input_summary=_compact(input_summary),
                    error=str(exc),
                )
            )
            raise


class WorkflowRunner:
    def __init__(self) -> None:
        self.mode = "langgraph" if self._langgraph_available() else "sequential"

    def run(self, initial_state: State, nodes: list[Node]) -> State:
        if self.mode == "langgraph":
            try:
                return self._run_langgraph(initial_state, nodes)
            except Exception:
                self.mode = "sequential-fallback"
        state = initial_state
        for _, node in nodes:
            state = node(state)
        return state

    def _run_langgraph(self, initial_state: State, nodes: list[Node]) -> State:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(dict)
        for name, node in nodes:
            graph.add_node(name, node)
        previous = START
        for name, _ in nodes:
            graph.add_edge(previous, name)
            previous = name
        graph.add_edge(previous, END)
        compiled = graph.compile()
        return compiled.invoke(initial_state)

    def _langgraph_available(self) -> bool:
        try:
            import langgraph  # noqa: F401

            return True
        except Exception:
            return False


def _compact(value: dict[str, Any]) -> dict[str, str | int | float | bool | None]:
    compacted: dict[str, str | int | float | bool | None] = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            compacted[key] = item[:160] if isinstance(item, str) else item
        elif isinstance(item, list):
            compacted[key] = len(item)
        elif isinstance(item, dict):
            compacted[key] = len(item)
        else:
            compacted[key] = item.__class__.__name__
    return compacted
