"""Diagnostic-only deadline reliability telemetry.

The observer never changes a deadline decision.  It compares independent clocks
so a timeout can be attributed to host suspension/contention or to a long
cooperative operation.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
import time
from typing import Callable, Iterator


Clock = Callable[[], float]


def windows_unbiased_interrupt_clock() -> tuple[Clock | None, str]:
    """Return the Windows active-time clock, or a portable unavailable marker."""

    if os.name != "nt":
        return None, "portable_unavailable"
    try:
        import ctypes

        query = ctypes.WinDLL("kernel32", use_last_error=True).QueryUnbiasedInterruptTime
        query.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]
        query.restype = ctypes.c_bool

        def read() -> float:
            value = ctypes.c_ulonglong()
            if not query(ctypes.byref(value)):
                raise OSError(ctypes.get_last_error(), "QueryUnbiasedInterruptTime failed")
            return value.value / 10_000_000.0

        read()  # fail closed during construction, not half-way through a run
        return read, "windows_query_unbiased_interrupt_time"
    except (AttributeError, OSError):
        return None, "windows_unavailable"


@dataclass(frozen=True)
class _ClockSample:
    wall: float
    monotonic: float
    process_cpu: float
    active: float | None


class DeadlineReliabilityObserver:
    """Collect bounded operation/checkpoint evidence without affecting search."""

    def __init__(
        self,
        *,
        enabled: bool,
        deadline_monotonic: float | None,
        wall_clock: Clock = time.time,
        monotonic_clock: Clock = time.perf_counter,
        process_clock: Clock = time.process_time,
        active_clock: Clock | None = None,
        active_clock_source: str = "portable_unavailable",
        long_operation_seconds: float = 1.0,
        suspend_detection_seconds: float = 1.0,
        contention_minimum_seconds: float = 1.0,
        contention_cpu_ratio: float = 0.25,
        clock_discontinuity_seconds: float = 1.0,
    ) -> None:
        self.enabled = enabled
        self.deadline_monotonic = deadline_monotonic
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._process_clock = process_clock
        self._active_clock = active_clock
        self._active_clock_source = active_clock_source
        self._long_operation_seconds = long_operation_seconds
        self._suspend_detection_seconds = suspend_detection_seconds
        self._contention_minimum_seconds = contention_minimum_seconds
        self._contention_cpu_ratio = contention_cpu_ratio
        self._clock_discontinuity_seconds = clock_discontinuity_seconds
        self._start = self._sample()
        self._last = self._start
        self._checkpoint_count = 0
        self._last_checkpoint: str | None = None
        self._last_operation: str | None = None
        self._max_operation: str | None = None
        self._max_operation_active_seconds = 0.0

    def _sample(self) -> _ClockSample:
        active = None
        if self._active_clock is not None:
            try:
                active = self._active_clock()
            except OSError:
                self._active_clock = None
                self._active_clock_source = "runtime_unavailable"
        return _ClockSample(
            wall=self._wall_clock(),
            monotonic=self._monotonic_clock(),
            process_cpu=self._process_clock(),
            active=active,
        )

    def checkpoint(self, name: str) -> None:
        if not self.enabled:
            return
        self._checkpoint_count += 1
        self._last_checkpoint = name

    @contextmanager
    def operation(self, name: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        before = self._sample()
        self._last_operation = name
        self._checkpoint_count += 1
        self._last_checkpoint = f"before_{name}"
        try:
            yield
        finally:
            after = self._sample()
            active_elapsed = (
                after.active - before.active
                if before.active is not None and after.active is not None
                else after.monotonic - before.monotonic
            )
            active_elapsed = max(0.0, active_elapsed)
            if active_elapsed > self._max_operation_active_seconds:
                self._max_operation_active_seconds = active_elapsed
                self._max_operation = name
            self._last = after
            self._checkpoint_count += 1
            self._last_checkpoint = f"after_{name}"

    def metadata(self) -> dict[str, object]:
        if not self.enabled:
            return {"deadline_reliability_enabled": False}
        end = self._sample()
        wall = max(0.0, end.wall - self._start.wall)
        monotonic = max(0.0, end.monotonic - self._start.monotonic)
        cpu = max(0.0, end.process_cpu - self._start.process_cpu)
        active = None
        if self._start.active is not None and end.active is not None:
            active = max(0.0, end.active - self._start.active)
        suspend = max(0.0, monotonic - active) if active is not None else None
        clock_delta = abs(wall - monotonic)
        if clock_delta > self._clock_discontinuity_seconds:
            classification = "CLOCK_DISCONTINUITY"
        elif suspend is not None and suspend > self._suspend_detection_seconds:
            classification = "SYSTEM_SUSPEND_DETECTED"
        elif (
            active is not None
            and active >= self._contention_minimum_seconds
            and cpu / max(active, 1e-12) < self._contention_cpu_ratio
        ):
            classification = "HOST_CONTENTION_SUSPECTED"
        elif self._max_operation_active_seconds > self._long_operation_seconds:
            classification = "LONG_NON_INTERRUPTIBLE_OPERATION"
        else:
            classification = "NORMAL"
        overshoot = 0.0
        if self.deadline_monotonic is not None:
            overshoot = max(0.0, end.monotonic - self.deadline_monotonic)
        environment_clean = classification not in {
            "SYSTEM_SUSPEND_DETECTED", "HOST_CONTENTION_SUSPECTED", "CLOCK_DISCONTINUITY",
        }
        return {
            "deadline_reliability_enabled": True,
            "deadline_reliability_classification": classification,
            "deadline_reliability_evidence_eligible": environment_clean,
            "deadline_reliability_deadline_overshoot_seconds": overshoot,
            "deadline_reliability_last_checkpoint": self._last_checkpoint,
            "deadline_reliability_last_operation": self._last_operation,
            "deadline_reliability_max_operation": self._max_operation,
            "deadline_reliability_max_operation_active_seconds": self._max_operation_active_seconds,
            "deadline_reliability_wall_elapsed_seconds": wall,
            "deadline_reliability_monotonic_elapsed_seconds": monotonic,
            "deadline_reliability_process_cpu_seconds": cpu,
            "deadline_reliability_active_elapsed_seconds": active,
            "deadline_reliability_suspend_seconds": suspend,
            "deadline_reliability_checkpoint_count": self._checkpoint_count,
            "deadline_reliability_active_clock_source": self._active_clock_source,
        }


def configured_deadline_observer(
    settings: dict[str, object],
    *,
    deadline_monotonic: float | None,
    monotonic_clock: Clock = time.perf_counter,
    wall_clock: Clock = time.time,
    process_clock: Clock = time.process_time,
    active_clock: Clock | None = None,
    active_clock_source: str | None = None,
) -> DeadlineReliabilityObserver:
    raw = settings.get("deadline_reliability", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("deadline_reliability must be a mapping")
    enabled = bool(raw.get("enabled", False))
    if active_clock_source is None:
        if active_clock is None and enabled:
            active_clock, active_clock_source = windows_unbiased_interrupt_clock()
        else:
            active_clock_source = "injected" if active_clock is not None else "disabled"
    numeric = {
        "long_operation_seconds": float(raw.get("long_operation_seconds", 1.0)),
        "suspend_detection_seconds": float(raw.get("suspend_detection_seconds", 1.0)),
        "contention_minimum_seconds": float(raw.get("contention_minimum_seconds", 1.0)),
        "contention_cpu_ratio": float(raw.get("contention_cpu_ratio", 0.25)),
        "clock_discontinuity_seconds": float(raw.get("clock_discontinuity_seconds", 1.0)),
    }
    if any(value <= 0 for value in numeric.values()):
        raise ValueError("deadline_reliability thresholds must be positive")
    if numeric["contention_cpu_ratio"] > 1:
        raise ValueError("deadline_reliability contention_cpu_ratio must be <= 1")
    return DeadlineReliabilityObserver(
        enabled=enabled,
        deadline_monotonic=deadline_monotonic,
        wall_clock=wall_clock,
        monotonic_clock=monotonic_clock,
        process_clock=process_clock,
        active_clock=active_clock,
        active_clock_source=active_clock_source,
        **numeric,
    )
