"""Registry of implemented mathematical level contracts."""

from __future__ import annotations

from pathlib import Path

from ..experiments.contracts import (
    ConstraintDefinition,
    LevelContract,
    LevelDefinition,
    LocalizedText,
    MathematicalExpression,
    VariableDefinition,
)
from . import level_01

_LEVELS = {
    "level_01": LevelDefinition(
        level_id="level_01",
        description="Fixed orientation; boundary, pairwise non-overlap, and payload constraints",
        default_config=Path("config/level_01/default.yaml"),
        supported_algorithms=(
            "milp_big_m", "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
            "extreme_point_simulated_annealing",
        ),
        run=level_01.run,
        prepare=level_01.prepare,
        validate_run=level_01.validate_run,
        contract=LevelContract(
            title=LocalizedText(
                vi="Level 1 — Xếp kiện 3D với hướng cố định",
                en="Level 1 — Fixed-orientation 3D container packing",
            ),
            problem=LocalizedText(
                vi=(
                    "Xếp mỗi kiện hộp chữ nhật đúng một lần vào các container không đồng nhất, "
                    "xác định tọa độ 3D và tối thiểu hóa số container được sử dụng."
                ),
                en=(
                    "Pack every rectangular item exactly once into heterogeneous containers, "
                    "choose its 3D coordinates, and minimize the containers used."
                ),
            ),
            notation=(
                MathematicalExpression(
                    expression_id="index_sets",
                    title=LocalizedText(vi="Tập chỉ số", en="Index sets"),
                    latex=r"I=\{1,\ldots,n\},\quad K=\{1,\ldots,m\},\quad P=\{(i,j)\in I^2:i<j\},\quad D=\{L,R,F,B,Dn,Up\}",
                    explanation=LocalizedText(
                        vi="I là tập kiện, K là tập container, P là tập cặp kiện và D là sáu hướng phân tách.",
                        en="I contains items, K containers, P item pairs, and D the six separation directions.",
                    ),
                    code_mapping="src/container_packing/models/level_01/constants.py; model_indices.py",
                ),
                MathematicalExpression(
                    expression_id="parameters",
                    title=LocalizedText(vi="Tham số kích thước, tải trọng và chi phí", en="Dimensions, payload, and cost parameters"),
                    latex=r"(\ell_i,w_i,h_i,q_i),\quad (L_k,W_k,H_k,Q_k,c_k)",
                    explanation=LocalizedText(
                        vi="Mỗi kiện có ba kích thước và khối lượng; mỗi container có ba kích thước, tải trọng tối đa và chi phí thực nghiệm.",
                        en="Each item has three dimensions and weight; each container has dimensions, maximum payload, and experimental cost.",
                    ),
                    code_mapping="src/container_packing/schemas.py::Item; Container",
                ),
                MathematicalExpression(
                    expression_id="big_m_and_priority",
                    title=LocalizedText(vi="Hằng số Big-M và độ ưu tiên", en="Big-M and priority constants"),
                    latex=r"M_x=\max_{k\in K}L_k,\quad M_y=\max_{k\in K}W_k,\quad M_z=\max_{k\in K}H_k,\quad B=1+\sum_{k\in K}c_k",
                    explanation=LocalizedText(
                        vi="Big-M được suy ra từ kích thước container; B làm cho giảm một container luôn quan trọng hơn mọi chênh lệch chi phí.",
                        en="Big-M values come from container dimensions; B makes reducing one container dominate every cost difference.",
                    ),
                    code_mapping="src/container_packing/models/level_01/milp_model.py::build_level1_model",
                ),
            ),
            objective=MathematicalExpression(
                expression_id="lexicographic_objective",
                title=LocalizedText(vi="Hàm mục tiêu", en="Objective function"),
                latex=r"\min\; B\sum_{k\in K}u_k+\sum_{k\in K}c_k u_k",
                explanation=LocalizedText(
                    vi="Ưu tiên tối thiểu số container, sau đó tối thiểu tổng chi phí container.",
                    en="Minimize used-container count first, then total container cost.",
                ),
                code_mapping="src/container_packing/models/level_01/milp_model.py::build_level1_model (objective)",
            ),
            variables=(
                VariableDefinition(
                    symbol="u[k]", latex=r"u_k\in\{0,1\}",
                    variable_type=LocalizedText(vi="Nhị phân", en="Binary"),
                    indices=LocalizedText(vi="container k", en="container k"),
                    meaning=LocalizedText(vi="Bằng 1 nếu container k được sử dụng.", en="Equals 1 when container k is used."),
                    code_mapping="src/container_packing/models/level_01/model_indices.py::ModelIndices.u",
                ),
                VariableDefinition(
                    symbol="a[i,k]", latex=r"a_{ik}\in\{0,1\}",
                    variable_type=LocalizedText(vi="Nhị phân", en="Binary"),
                    indices=LocalizedText(vi="kiện i, container k", en="item i, container k"),
                    meaning=LocalizedText(vi="Bằng 1 nếu kiện i được gán vào container k.", en="Equals 1 when item i is assigned to container k."),
                    code_mapping="src/container_packing/models/level_01/model_indices.py::ModelIndices.a",
                ),
                VariableDefinition(
                    symbol="x[i], y[i], z[i]", latex=r"x_i,y_i,z_i\ge 0",
                    variable_type=LocalizedText(vi="Liên tục", en="Continuous"),
                    indices=LocalizedText(vi="kiện i", en="item i"),
                    meaning=LocalizedText(
                        vi="Tọa độ góc dưới-trái-sau của kiện i, đơn vị mm và không xoay.",
                        en="Lower-left-back coordinates of fixed-orientation item i in mm.",
                    ),
                    code_mapping="src/container_packing/models/level_01/model_indices.py::ModelIndices.x/y/z",
                ),
                VariableDefinition(
                    symbol="delta[i,j,k,d]", latex=r"\delta_{ijkd}\in\{0,1\}",
                    variable_type=LocalizedText(vi="Nhị phân", en="Binary"),
                    indices=LocalizedText(vi="cặp kiện (i,j), container k, hướng d", en="item pair (i,j), container k, direction d"),
                    meaning=LocalizedText(
                        vi="Kích hoạt một trong sáu hướng phân tách cho hai kiện cùng container.",
                        en="Activates one of six separation directions for co-located items.",
                    ),
                    code_mapping="src/container_packing/models/level_01/model_indices.py::ModelIndices.delta",
                ),
            ),
            active_constraints=(
                ConstraintDefinition(
                    "exact_assignment", LocalizedText(vi="Gán chính xác một lần", en="Exact assignment"),
                    r"\sum_{k\in K}a_{ik}=1\quad\forall i\in I",
                    LocalizedText(vi="Mỗi kiện bắt buộc thuộc đúng một container.", en="Every required item belongs to exactly one container."),
                    "src/container_packing/models/level_01/milp_model.py::build_level1_model (R1)",
                ),
                ConstraintDefinition(
                    "container_activation", LocalizedText(vi="Kích hoạt container", en="Container activation"),
                    r"a_{ik}\le u_k\quad\forall i\in I,\;k\in K",
                    LocalizedText(vi="Chỉ được gán kiện vào container đã mở.", en="An item can be assigned only to an opened container."),
                    "src/container_packing/models/level_01/milp_model.py::build_level1_model (R2)",
                ),
                ConstraintDefinition(
                    "boundaries", LocalizedText(vi="Giới hạn biên container", en="Container boundaries"),
                    r"\begin{aligned}x_i+\ell_i&\le L_k+M_x(1-a_{ik})\\y_i+w_i&\le W_k+M_y(1-a_{ik})\\z_i+h_i&\le H_k+M_z(1-a_{ik})\end{aligned}\quad\forall i,k",
                    LocalizedText(vi="Nếu kiện i thuộc k, toàn bộ kiện phải nằm trong ba biên của container.", en="If item i belongs to k, it must remain inside all three container bounds."),
                    "src/container_packing/models/level_01/milp_model.py::build_level1_model (R3-R5)",
                ),
                ConstraintDefinition(
                    "payload", LocalizedText(vi="Tải trọng tối đa", en="Maximum payload"),
                    r"\sum_{i\in I}q_i a_{ik}\le Q_k u_k\quad\forall k\in K",
                    LocalizedText(vi="Tổng khối lượng kiện không vượt tải trọng container.", en="The loaded item weight cannot exceed container payload."),
                    "src/container_packing/models/level_01/milp_model.py::build_level1_model (R6)",
                ),
                ConstraintDefinition(
                    "direction_linking", LocalizedText(vi="Liên kết hướng phân tách", en="Separation-direction linking"),
                    r"\delta_{ijkd}\le a_{ik},\quad\delta_{ijkd}\le a_{jk}\quad\forall(i,j)\in P,k,d",
                    LocalizedText(vi="Một hướng chỉ được kích hoạt khi cả hai kiện cùng thuộc container k.", en="A direction can activate only when both items are assigned to container k."),
                    "src/container_packing/models/level_01/milp_model.py::build_level1_model (R7)",
                ),
                ConstraintDefinition(
                    "separation_activation", LocalizedText(vi="Kích hoạt phép tuyển", en="Separation disjunction activation"),
                    r"\sum_{d\in D}\delta_{ijkd}\ge a_{ik}+a_{jk}-1\quad\forall(i,j)\in P,k",
                    LocalizedText(vi="Hai kiện cùng container phải có ít nhất một hướng phân tách.", en="Two items in the same container require at least one separation direction."),
                    "src/container_packing/models/level_01/milp_model.py::build_level1_model (R8)",
                ),
                ConstraintDefinition(
                    "pairwise_non_overlap", LocalizedText(vi="Không chồng lấn theo sáu hướng", en="Six-direction pairwise non-overlap"),
                    r"\begin{aligned}x_i+\ell_i&\le x_j+M_x(1-\delta_{ijkL})\\x_j+\ell_j&\le x_i+M_x(1-\delta_{ijkR})\\y_i+w_i&\le y_j+M_y(1-\delta_{ijkF})\\y_j+w_j&\le y_i+M_y(1-\delta_{ijkB})\\z_i+h_i&\le z_j+M_z(1-\delta_{ijkDn})\\z_j+h_j&\le z_i+M_z(1-\delta_{ijkUp})\end{aligned}\quad\forall(i,j)\in P,\;k\in K",
                    LocalizedText(vi="Mỗi delta được chọn đặt một kiện hoàn toàn về một phía của kiện kia.", en="Each selected delta places one item completely on one side of the other."),
                    "src/container_packing/models/level_01/milp_model.py::build_level1_model (R9)",
                ),
            ),
            inactive_constraints=tuple(LocalizedText(vi=vi, en=en) for vi, en in (
                ("xoay kiện", "rotation"), ("bề mặt đỡ", "support"), ("tiếp xúc sàn", "floor contact"),
                ("ổn định vật lý", "stability"), ("khả năng chồng", "stackability"),
                ("hàng dễ vỡ", "fragility"), ("trọng tâm", "center of gravity"),
                ("thứ tự xếp hàng", "loading order"), ("thứ tự dỡ hàng", "unloading order"),
            )),
            assumptions=(
                LocalizedText(vi="Dữ liệu offline và mỗi container cấu hình là một bản thể vật lý.", en="Offline input and one physical instance per configured container."),
                LocalizedText(vi="Các kiện là hình hộp chữ nhật với hướng đặt cố định.", en="Rectangular cuboids with fixed orientation."),
                LocalizedText(vi="Kích thước dùng millimeter và khối lượng dùng kilogram.", en="Dimensions use millimeters and weights use kilograms."),
            ),
            limitations=(
                LocalizedText(vi="Trạng thái FEASIBLE của heuristic không chứng minh tối ưu toàn cục.", en="Heuristic FEASIBLE status is not a proof of global optimality."),
                LocalizedText(vi="Hợp lệ hình học không đồng nghĩa phương án ổn định vật lý.", en="Geometric feasibility does not imply a physically stable loading plan."),
            ),
            solution_claim=LocalizedText(
                vi="Nghiệm hợp lệ về hình học và tải trọng theo giả định Level 1.",
                en="A geometrically and payload-feasible solution under Level 1 assumptions.",
            ),
        ),
    ),
}


def list_levels() -> tuple[LevelDefinition, ...]:
    return tuple(_LEVELS[key] for key in sorted(_LEVELS))


def get_level(level_id: str) -> LevelDefinition:
    try:
        return _LEVELS[level_id]
    except KeyError as exc:
        available = ", ".join(sorted(_LEVELS))
        raise ValueError(f"Level {level_id!r} is not implemented. Available: {available}") from exc
