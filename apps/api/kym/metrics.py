"""Lightweight in-process metrics with real measured latencies (p50/p95/p99). No fabricated numbers."""
from __future__ import annotations

import threading
from collections import defaultdict


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.lat: dict[str, list[float]] = defaultdict(list)
        self.counters: dict[str, int] = defaultdict(int)

    def observe(self, name: str, ms: float) -> None:
        with self._lock:
            self.lat[name].append(ms)
            if len(self.lat[name]) > 20000:
                del self.lat[name][:10000]

    def count(self, name: str, n: int = 1) -> None:
        with self._lock:
            self.counters[name] += n

    @staticmethod
    def pct(vals: list[float], p: float) -> float:
        if not vals:
            return 0.0
        v = sorted(vals)
        return round(v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))], 3)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "latency_ms": {k: {"n": len(v), "p50": self.pct(v, 50), "p95": self.pct(v, 95), "p99": self.pct(v, 99)} for k, v in self.lat.items()},
                "counters": dict(self.counters),
            }

    def reset(self) -> None:
        with self._lock:
            self.lat.clear()
            self.counters.clear()


METRICS = Metrics()
