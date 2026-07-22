"""Contiguous Level 2 indices extending the fixed-orientation Level 1 vector."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..common.constants import Direction
from ..level_01.model_indices import ModelIndices


@dataclass(frozen=True)
class Level02ModelIndices:
    n_items: int
    n_containers: int
    grid_x: int
    grid_y: int
    base: ModelIndices = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.grid_x <= 0 or self.grid_y <= 0:
            raise ValueError("support grid dimensions must be positive")
        object.__setattr__(self, "base", ModelIndices(self.n_items, self.n_containers))

    @property
    def n_pairs(self) -> int:
        return self.base.n_pairs

    @property
    def n_ordered_pairs(self) -> int:
        return self.n_items * (self.n_items - 1)

    @property
    def grid_size(self) -> int:
        return self.grid_x * self.grid_y

    @property
    def floor_count(self) -> int:
        return self.n_items * self.n_containers

    @property
    def support_point_count(self) -> int:
        return self.n_ordered_pairs * self.n_containers * self.grid_size

    @property
    def center_support_count(self) -> int:
        return self.n_ordered_pairs * self.n_containers

    @property
    def n_variables(self) -> int:
        return self.base.n_variables + self.floor_count + self.support_point_count + self.center_support_count

    def u(self, k: int) -> int:
        return self.base.u(k)

    def a(self, i: int, k: int) -> int:
        return self.base.a(i, k)

    def x(self, i: int) -> int:
        return self.base.x(i)

    def y(self, i: int) -> int:
        return self.base.y(i)

    def z(self, i: int) -> int:
        return self.base.z(i)

    def delta(self, i: int, j: int, k: int, direction: Direction | str) -> int:
        return self.base.delta(i, j, k, direction)

    def ordered_pair_number(self, i: int, j: int) -> int:
        self.base._check(i, self.n_items, "item")
        self.base._check(j, self.n_items, "supporting item")
        if i == j:
            raise IndexError("an item cannot support itself")
        return i * (self.n_items - 1) + (j if j < i else j - 1)

    def floor(self, i: int, k: int) -> int:
        self.base._check(i, self.n_items, "item")
        self.base._check(k, self.n_containers, "container")
        return self.base.n_variables + i * self.n_containers + k

    def support_point(self, i: int, j: int, k: int, p: int, q: int) -> int:
        self.base._check(k, self.n_containers, "container")
        self.base._check(p, self.grid_x, "grid x")
        self.base._check(q, self.grid_y, "grid y")
        pair = self.ordered_pair_number(i, j)
        offset = ((pair * self.n_containers + k) * self.grid_x + p) * self.grid_y + q
        return self.base.n_variables + self.floor_count + offset

    def center_support(self, i: int, j: int, k: int) -> int:
        self.base._check(k, self.n_containers, "container")
        pair = self.ordered_pair_number(i, j)
        return self.base.n_variables + self.floor_count + self.support_point_count + pair * self.n_containers + k
