"""Contiguous vector-index mapping for every Level 1 MILP variable."""

from __future__ import annotations

from dataclasses import dataclass

from .constants import DIRECTIONS, Direction


@dataclass(frozen=True)
class ModelIndices:
    n_items: int
    n_containers: int

    def __post_init__(self) -> None:
        if self.n_items <= 0 or self.n_containers <= 0:
            raise ValueError("n_items and n_containers must be positive")

    @property
    def n_pairs(self) -> int:
        return self.n_items * (self.n_items - 1) // 2

    @property
    def n_variables(self) -> int:
        return self.n_containers + self.n_items * self.n_containers + 3 * self.n_items + self.n_pairs * self.n_containers * 6

    def u(self, k: int) -> int:
        self._check(k, self.n_containers, "container")
        return k

    def a(self, i: int, k: int) -> int:
        self._check(i, self.n_items, "item"); self._check(k, self.n_containers, "container")
        return self.n_containers + i * self.n_containers + k

    def x(self, i: int) -> int:
        self._check(i, self.n_items, "item")
        return self.n_containers + self.n_items * self.n_containers + i

    def y(self, i: int) -> int:
        return self.x(i) + self.n_items

    def z(self, i: int) -> int:
        return self.x(i) + 2 * self.n_items

    def pair_number(self, i: int, j: int) -> int:
        if not 0 <= i < j < self.n_items:
            raise IndexError(f"Expected 0 <= i < j < {self.n_items}, got ({i}, {j})")
        return i * (2 * self.n_items - i - 1) // 2 + (j - i - 1)

    def delta(self, i: int, j: int, k: int, direction: Direction | str) -> int:
        self._check(k, self.n_containers, "container")
        try:
            d = Direction(direction)
        except ValueError as exc:
            raise KeyError(f"Unknown direction: {direction}") from exc
        base = self.n_containers + self.n_items * self.n_containers + 3 * self.n_items
        return base + ((self.pair_number(i, j) * self.n_containers + k) * 6 + DIRECTIONS.index(d))

    @staticmethod
    def _check(value: int, upper: int, label: str) -> None:
        if not 0 <= value < upper:
            raise IndexError(f"{label} index {value} outside [0, {upper})")
