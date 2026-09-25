"""Resource monitor interfaces and a deterministic simulated implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class NodeState:
    node: str
    available_models: tuple[str, ...]
    gpu_utilization: float
    total_vram_gb: float
    free_vram_gb: float
    queue_length: int
    network_latency_ms: float
    throughput_tokens_per_sec: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.gpu_utilization <= 1.0:
            raise ValueError("gpu_utilization must be in [0, 1]")
        if not 0.0 <= self.free_vram_gb <= self.total_vram_gb:
            raise ValueError("free_vram_gb must be between 0 and total_vram_gb")
        if self.queue_length < 0:
            raise ValueError("queue_length cannot be negative")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["available_models"] = list(self.available_models)
        return data


class ResourceMonitor(ABC):
    @abstractmethod
    def snapshot(self) -> dict[str, NodeState]:
        """Return a point-in-time resource state keyed by node name."""


class SimulatedResourceMonitor(ResourceMonitor):
    """In-memory monitor for experiments without access to real GPUs."""

    def __init__(self, states: Iterable[NodeState]):
        self._states = {state.node: state for state in states}
        if not self._states:
            raise ValueError("At least one node state is required")
        self.last_snapshot_at: str | None = None

    def snapshot(self) -> dict[str, NodeState]:
        self.last_snapshot_at = datetime.now(timezone.utc).isoformat()
        return dict(self._states)

    def update(self, node: str, **changes) -> None:
        if node not in self._states:
            raise KeyError(node)
        self._states[node] = replace(self._states[node], **changes)

