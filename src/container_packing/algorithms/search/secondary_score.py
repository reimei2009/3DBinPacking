"""Search score phụ chuẩn hóa cho candidate đã hợp lệ."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from ..contracts import SecondarySearchScore
from ...geometry.support import evaluate_support
from ...metrics import placement_signature
from ...schemas import Container, Placement


def calculate_secondary_search_score(
    placements: Sequence[Placement],
    containers: Sequence[Container],
    *,
    support_threshold: float | None,
    support_epsilon_mm: float = 1e-4,
) -> SecondarySearchScore:
    """Tính KPI phụ trên nghiệm complete và đã được validator chấp nhận.

    Level 1 không kích hoạt support, vì vậy thành phần support được giữ trung
    tính bằng 0 thay vì âm thầm đưa constraint Level 2 vào Level 1.
    """

    if not placements:
        raise ValueError("secondary search score requires at least one placement")
    if support_threshold is not None and not 0 < support_threshold <= 1:
        raise ValueError("support_threshold must be in (0, 1]")
    if support_epsilon_mm <= 0:
        raise ValueError("support_epsilon_mm must be positive")

    container_by_id = {value.container_id: value for value in containers}
    grouped: dict[str, list[Placement]] = defaultdict(list)
    for placement in placements:
        if placement.container_id not in container_by_id:
            raise ValueError(
                f"Secondary score references unknown container {placement.container_id}"
            )
        grouped[placement.container_id].append(placement)

    concentrations: list[float] = []
    total_internal_void_mm3 = 0.0
    total_container_volume_mm3 = 0.0
    support_margins: list[float] = []
    for container_id in sorted(grouped):
        values = grouped[container_id]
        container = container_by_id[container_id]
        container_volume_mm3 = (
            container.length_mm * container.width_mm * container.height_mm
        )
        loaded_volume_mm3 = sum(
            value.length_mm * value.width_mm * value.height_mm for value in values
        )
        loaded_weight_kg = sum(value.weight_kg for value in values)
        volume_utilization = loaded_volume_mm3 / max(container_volume_mm3, 1e-12)
        payload_utilization = loaded_weight_kg / max(container.max_weight_kg, 1e-12)
        concentrations.append(
            (volume_utilization ** 2 + payload_utilization ** 2) / 2.0
        )

        max_x = max(value.x_mm + value.length_mm for value in values)
        max_y = max(value.y_mm + value.width_mm for value in values)
        max_z = max(value.z_mm + value.height_mm for value in values)
        bounding_volume_mm3 = max_x * max_y * max_z
        total_internal_void_mm3 += max(
            bounding_volume_mm3 - loaded_volume_mm3, 0.0
        )
        total_container_volume_mm3 += container_volume_mm3

        if support_threshold is not None:
            for placement in values:
                support = evaluate_support(
                    placement, values, epsilon_mm=support_epsilon_mm,
                )
                support_margins.append(
                    support.exact_support_ratio - support_threshold
                )

    utilization_concentration = sum(concentrations) / len(concentrations)
    internal_void_ratio = total_internal_void_mm3 / max(
        total_container_volume_mm3, 1e-12
    )
    minimum_support_margin = min(support_margins, default=0.0)
    return SecondarySearchScore(
        negative_utilization_concentration=-utilization_concentration,
        internal_void_ratio=internal_void_ratio,
        negative_minimum_support_margin=-minimum_support_margin,
        placement_signature=placement_signature(list(placements)),
    )
