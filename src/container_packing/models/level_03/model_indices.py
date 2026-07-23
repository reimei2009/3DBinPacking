"""Level 3 indices: Level 2 support variables plus horizontal orientation."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..level_02.model_indices import Level02ModelIndices


@dataclass(frozen=True)
class Level03ModelIndices:
    n_items: int
    n_containers: int
    grid_x: int
    grid_y: int
    base: Level02ModelIndices = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "base", Level02ModelIndices(
            self.n_items, self.n_containers, self.grid_x, self.grid_y,
        ))

    @property
    def n_pairs(self) -> int:
        return self.base.n_pairs

    @property
    def grid_size(self) -> int:
        return self.base.grid_size

    @property
    def floor_count(self) -> int:
        return self.base.floor_count

    @property
    def support_point_count(self) -> int:
        return self.base.support_point_count

    @property
    def center_support_count(self) -> int:
        return self.base.center_support_count

    @property
    def orientation_count(self) -> int:
        return self.n_items * 2

    @property
    def n_variables(self) -> int:
        return self.base.n_variables + self.orientation_count

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

    def delta(self, i: int, j: int, k: int, direction):
        return self.base.delta(i, j, k, direction)

    def floor(self, i: int, k: int) -> int:
        return self.base.floor(i, k)

    def support_point(self, i: int, j: int, k: int, p: int, q: int) -> int:
        return self.base.support_point(i, j, k, p, q)

    def center_support(self, i: int, j: int, k: int) -> int:
        return self.base.center_support(i, j, k)

    def orientation(self, i: int, code_index: int) -> int:
        if not 0 <= i < self.n_items:
            raise IndexError(f"item index {i} is outside [0, {self.n_items})")
        if code_index not in (0, 1):
            raise IndexError("orientation code index must be 0 (XYZ) or 1 (YXZ)")
        return self.base.n_variables + i * 2 + code_index
