"""Đo peak RSS nhẹ cho benchmark; không thay đổi solver semantics."""

from __future__ import annotations

from threading import Event, Thread

import psutil


class PeakMemorySampler:
    """Lấy mẫu RSS của process hiện tại trong một phase có giới hạn."""

    def __init__(self, interval_seconds: float = 0.01) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._interval = interval_seconds
        self._stop = Event()
        self._thread: Thread | None = None
        self._process = psutil.Process()
        self.peak_rss_bytes = 0

    def __enter__(self) -> "PeakMemorySampler":
        self._sample()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, self._interval * 4))
        self._sample()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._sample()

    def _sample(self) -> None:
        try:
            self.peak_rss_bytes = max(
                self.peak_rss_bytes, int(self._process.memory_info().rss),
            )
        except (psutil.Error, OSError):
            # Memory telemetry không được phép làm hỏng benchmark solver.
            return
