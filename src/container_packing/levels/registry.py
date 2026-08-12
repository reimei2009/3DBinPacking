"""Registry of implemented mathematical level contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..experiments.contracts import (
    ConstraintDefinition,
    LevelContract,
    LevelDefinition,
    LocalizedText,
    MathematicalExpression,
    VariableDefinition,
)
from . import level_01, level_02, level_03, level_04, level_05, level_06, level_07, level_08

_LEVELS = {
    "level_01": LevelDefinition(
        level_id="level_01",
        description="Fixed orientation; boundary, pairwise non-overlap, and payload constraints",
        default_config=Path("config/level_01/default.yaml"),
        supported_algorithms=(
            "milp_big_m", "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_ffd_gap_fill",
            "extreme_point_best_fit_projected_ep", "extreme_point_ffd_projected_ep", "extreme_point_hill_climbing",
            "extreme_point_simulated_annealing", "maximal_space_best_fit",
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
                    code_mapping="src/container_packing/models/common/fixed_orientation_milp.py::build_fixed_orientation_assembly",
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
                code_mapping="src/container_packing/models/common/fixed_orientation_milp.py::build_fixed_orientation_assembly (objective)",
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
                    "src/container_packing/models/common/fixed_orientation_milp.py::build_fixed_orientation_assembly (R1)",
                ),
                ConstraintDefinition(
                    "container_activation", LocalizedText(vi="Kích hoạt container", en="Container activation"),
                    r"a_{ik}\le u_k\quad\forall i\in I,\;k\in K",
                    LocalizedText(vi="Chỉ được gán kiện vào container đã mở.", en="An item can be assigned only to an opened container."),
                    "src/container_packing/models/common/fixed_orientation_milp.py::build_fixed_orientation_assembly (R2)",
                ),
                ConstraintDefinition(
                    "boundaries", LocalizedText(vi="Giới hạn biên container", en="Container boundaries"),
                    r"\begin{aligned}x_i+\ell_i&\le L_k+M_x(1-a_{ik})\\y_i+w_i&\le W_k+M_y(1-a_{ik})\\z_i+h_i&\le H_k+M_z(1-a_{ik})\end{aligned}\quad\forall i,k",
                    LocalizedText(vi="Nếu kiện i thuộc k, toàn bộ kiện phải nằm trong ba biên của container.", en="If item i belongs to k, it must remain inside all three container bounds."),
                    "src/container_packing/models/common/fixed_orientation_milp.py::build_fixed_orientation_assembly (R3-R5)",
                ),
                ConstraintDefinition(
                    "payload", LocalizedText(vi="Tải trọng tối đa", en="Maximum payload"),
                    r"\sum_{i\in I}q_i a_{ik}\le Q_k u_k\quad\forall k\in K",
                    LocalizedText(vi="Tổng khối lượng kiện không vượt tải trọng container.", en="The loaded item weight cannot exceed container payload."),
                    "src/container_packing/models/common/fixed_orientation_milp.py::build_fixed_orientation_assembly (R6)",
                ),
                ConstraintDefinition(
                    "direction_linking", LocalizedText(vi="Liên kết hướng phân tách", en="Separation-direction linking"),
                    r"\delta_{ijkd}\le a_{ik},\quad\delta_{ijkd}\le a_{jk}\quad\forall(i,j)\in P,k,d",
                    LocalizedText(vi="Một hướng chỉ được kích hoạt khi cả hai kiện cùng thuộc container k.", en="A direction can activate only when both items are assigned to container k."),
                    "src/container_packing/models/common/fixed_orientation_milp.py::build_fixed_orientation_assembly (R7)",
                ),
                ConstraintDefinition(
                    "separation_activation", LocalizedText(vi="Kích hoạt phép tuyển", en="Separation disjunction activation"),
                    r"\sum_{d\in D}\delta_{ijkd}\ge a_{ik}+a_{jk}-1\quad\forall(i,j)\in P,k",
                    LocalizedText(vi="Hai kiện cùng container phải có ít nhất một hướng phân tách.", en="Two items in the same container require at least one separation direction."),
                    "src/container_packing/models/common/fixed_orientation_milp.py::build_fixed_orientation_assembly (R8)",
                ),
                ConstraintDefinition(
                    "pairwise_non_overlap", LocalizedText(vi="Không chồng lấn theo sáu hướng", en="Six-direction pairwise non-overlap"),
                    r"\begin{aligned}x_i+\ell_i&\le x_j+M_x(1-\delta_{ijkL})\\x_j+\ell_j&\le x_i+M_x(1-\delta_{ijkR})\\y_i+w_i&\le y_j+M_y(1-\delta_{ijkF})\\y_j+w_j&\le y_i+M_y(1-\delta_{ijkB})\\z_i+h_i&\le z_j+M_z(1-\delta_{ijkDn})\\z_j+h_j&\le z_i+M_z(1-\delta_{ijkUp})\end{aligned}\quad\forall(i,j)\in P,\;k\in K",
                    LocalizedText(vi="Mỗi delta được chọn đặt một kiện hoàn toàn về một phía của kiện kia.", en="Each selected delta places one item completely on one side of the other."),
                    "src/container_packing/models/common/fixed_orientation_milp.py::build_fixed_orientation_assembly (R9)",
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


# Level 5 is registered later in this declarative module. The Level 6 entry is
# completed from that contract after all prior levels have been constructed.
_LEVEL_05_CONTRACT = _LEVELS["level_01"].contract
_LEVELS["level_06"] = LevelDefinition(
    level_id="level_06",
    description="Experimental explicit nesting through deterministic compound-root constructive heuristics",
    default_config=Path("config/level_06/experimental.yaml"),
    supported_algorithms=(
        "extreme_point_ffd_nesting_fixture",
        "extreme_point_best_fit_nesting_fixture",
        "extreme_point_hill_climbing_nesting_fixture",
        "extreme_point_simulated_annealing_nesting_fixture",
    ),
    run=level_06.run,
    prepare=level_06.prepare,
    validate_run=level_06.validate_run,
    contract=LevelContract(
        title=LocalizedText(
            vi="Level 6 — Nesting tường minh (thử nghiệm)",
            en="Level 6 — Explicit nesting (experimental)",
        ),
        problem=LocalizedText(
            vi="Xếp compound root tạo từ các quan hệ host–child đã khai báo rõ; child là logical member.",
            en="Pack compound roots formed from explicit host-child relations; children are logical members.",
        ),
        notation=_LEVEL_05_CONTRACT.notation + (
            MathematicalExpression(
                "nesting_relation",
                LocalizedText(vi="Quan hệ lồng", en="Nesting relation"),
                r"n_{hi}=1\Longleftrightarrow i\text{ is nested in host }h",
                LocalizedText(
                    vi="Quan hệ chỉ được tạo khi metadata compatibility, kích thước trong và depth hợp lệ.",
                    en="A relation exists only with compatible metadata, inner dimensions and valid depth.",
                ),
                "src/container_packing/levels/nesting_construction.py::construct_nesting_relations",
            ),
        ),
        objective=_LEVEL_05_CONTRACT.objective,
        variables=_LEVEL_05_CONTRACT.variables + (
            VariableDefinition(
                "n[h,i]",
                r"n_{hi}\in\{0,1\}",
                LocalizedText(vi="Quan hệ rời rạc suy ra", en="Derived discrete relation"),
                LocalizedText(vi="host h, child i", en="host h, child i"),
                LocalizedText(
                    vi="Biểu diễn child i là thành viên logical của host h trong compound.",
                    en="Represents child i as a logical member of host h's compound.",
                ),
                "src/container_packing/levels/nesting_engine.py::NestingRelation",
            ),
        ),
        active_constraints=_LEVEL_05_CONTRACT.active_constraints + (
            ConstraintDefinition(
                "explicit_nesting_compatibility",
                LocalizedText(vi="Tương thích lồng tường minh", en="Explicit nesting compatibility"),
                r"n_{hi}=1\Rightarrow g_h=g_i,\;d_i\preceq d_h^{inner},\;\operatorname{depth}(i)\le D_h",
                LocalizedText(
                    vi="Group, role, kích thước trong và giới hạn depth phải hợp lệ trước khi tạo compound.",
                    en="Group, role, inner dimensions and depth must be valid before creating a compound.",
                ),
                "src/container_packing/levels/nesting.py::NestingCapabilityProvider",
            ),
            ConstraintDefinition(
                "compound_root_external_geometry",
                LocalizedText(vi="Hình học ngoài theo compound root", en="Compound-root external geometry"),
                r"H_{root}^{eff}=h_{root}+\sum_{i\in chain(root)\setminus\{root\}}\Delta h_i",
                LocalizedText(
                    vi="Chỉ envelope root là đối tượng boundary, non-overlap, support, stack và load ở bên ngoài.",
                    en="Only the root envelope participates in external boundary, non-overlap, support, stack and load checks.",
                ),
                "src/container_packing/levels/level_06_compound_validation.py::validate_compound_geometry",
            ),
        ),
        inactive_constraints=tuple(
            value for value in _LEVEL_05_CONTRACT.inactive_constraints if value.en != "nesting"
        ) + (
            LocalizedText(vi="truyền tải nội bộ khi lồng", en="internal nesting load transfer"),
            LocalizedText(vi="xoay orientation-aware khi lồng", en="orientation-aware nesting"),
            LocalizedText(vi="ổn định vật lý đầy đủ", en="full physical stability"),
        ),
        assumptions=_LEVEL_05_CONTRACT.assumptions + (
            LocalizedText(
                vi="Chỉ metadata nesting khai báo rõ được kích hoạt; dữ liệu thiếu metadata vẫn là non-nesting.",
                en="Only explicitly declared nesting metadata is active; missing metadata remains non-nesting.",
            ),
        ),
        limitations=(
            LocalizedText(
                vi="FFD, Best Fit, Hill Climbing và SA là portfolio experimental; chưa có practical default hay benchmark quy mô lớn.",
                en="FFD, Best Fit, Hill Climbing and SA form an experimental portfolio without a practical default or large-scale benchmark.",
            ),
            LocalizedText(
                vi="Chưa mô hình hóa lực, áp suất, contact nội bộ hoặc orientation-aware nesting.",
                en="Internal forces, pressure, internal contacts and orientation-aware nesting are not modeled.",
            ),
        ),
        solution_claim=LocalizedText(
            vi="Nghiệm experimental hợp lệ độc lập theo compound geometry và ràng buộc ngoài kế thừa.",
            en="An independently valid experimental solution under compound geometry and inherited external constraints.",
        ),
    ),
)


_LEVEL_01_CONTRACT = _LEVELS["level_01"].contract
_LEVELS["level_02"] = LevelDefinition(
    level_id="level_02",
    description="Fixed orientation plus floor contact, minimum base support, and center support",
    default_config=Path("config/level_02/default.yaml"),
    supported_algorithms=(
        "milp_big_m", "extreme_point_best_fit", "extreme_point_ffd",
        "extreme_point_hill_climbing", "extreme_point_simulated_annealing",
        "maximal_space_best_fit",
    ),
    run=level_02.run,
    prepare=level_02.prepare,
    validate_run=level_02.validate_run,
    contract=LevelContract(
        title=LocalizedText(
            vi="Level 2 — Ràng buộc hỗ trợ hình học",
            en="Level 2 — Geometric support constraints",
        ),
        problem=LocalizedText(
            vi=(
                "Kế thừa Level 1 và yêu cầu mỗi kiện nằm trên sàn hoặc được các mặt trên bên dưới "
                "hỗ trợ đủ tỷ lệ đáy và hỗ trợ tâm đáy."
            ),
            en=(
                "Extend Level 1 so every item is on the floor or has sufficient base-area and "
                "base-center support from top faces below."
            ),
        ),
        notation=_LEVEL_01_CONTRACT.notation + (
            MathematicalExpression(
                "support_parameters", LocalizedText(vi="Tham số support", en="Support parameters"),
                r"G=G_xG_y,quad r\in(0,1],quad N_{min}=\lceil rG\rceil",
                LocalizedText(
                    vi="G là số điểm grid, r là ngưỡng tỷ lệ hỗ trợ và Nmin là số điểm tối thiểu.",
                    en="G is the grid size, r the support threshold, and Nmin the required point count.",
                ),
                "config/level_02/default.yaml::support",
            ),
        ),
        objective=_LEVEL_01_CONTRACT.objective,
        variables=_LEVEL_01_CONTRACT.variables + (
            VariableDefinition(
                "floor[i,k]", r"f_{ik}\in\{0,1\}", LocalizedText(vi="Nhị phân", en="Binary"),
                LocalizedText(vi="kiện i, container k", en="item i, container k"),
                LocalizedText(vi="Bằng 1 khi kiện nằm trực tiếp trên sàn.", en="Equals 1 when the item is directly on the floor."),
                "src/container_packing/models/level_02/model_indices.py::Level02ModelIndices.floor",
            ),
            VariableDefinition(
                "support_point[i,j,k,p,q]", r"s_{ijkpq}\in\{0,1\}",
                LocalizedText(vi="Nhị phân", en="Binary"),
                LocalizedText(vi="i khác j, container k, điểm grid (p,q)", en="i distinct from j, container k, grid point (p,q)"),
                LocalizedText(vi="Điểm grid dưới i được mặt trên của j hỗ trợ.", en="A base-grid point of i is supported by j's top face."),
                "src/container_packing/models/level_02/model_indices.py::Level02ModelIndices.support_point",
            ),
            VariableDefinition(
                "center_support[i,j,k]", r"c_{ijk}\in\{0,1\}",
                LocalizedText(vi="Nhị phân", en="Binary"),
                LocalizedText(vi="i khác j, container k", en="i distinct from j, container k"),
                LocalizedText(vi="Tâm đáy i được mặt trên j hỗ trợ.", en="The base center of i is supported by j's top face."),
                "src/container_packing/models/level_02/model_indices.py::Level02ModelIndices.center_support",
            ),
        ),
        active_constraints=_LEVEL_01_CONTRACT.active_constraints + (
            ConstraintDefinition(
                "aggregate_volume_capacity",
                LocalizedText(vi="Giới hạn thể tích tổng hợp", en="Aggregate volume capacity"),
                r"\sum_i \frac{v_i}{V_k}a_{ik}\le u_k\quad\forall k\in K",
                LocalizedText(
                    vi="Bất đẳng thức dư thừa giúp relaxation nhận biết trực tiếp sức chứa thể tích.",
                    en="A redundant valid inequality that exposes volume capacity to the relaxation.",
                ),
                "src/container_packing/models/common/fixed_orientation_milp.py::add_capacity_strengthening_cuts",
            ),
            ConstraintDefinition(
                "global_capacity_lower_bounds",
                LocalizedText(vi="Cận dưới sức chứa toàn cục", en="Global capacity lower bounds"),
                r"\sum_k V_k u_k\ge\sum_i v_i,\quad \sum_k Q_k u_k\ge\sum_i q_i,\quad \sum_k u_k\ge LB",
                LocalizedText(
                    vi="Công khai các cận dưới thể tích, tải trọng và số container cho solver.",
                    en="Explicit global volume, payload, and container-count lower bounds for the solver.",
                ),
                "src/container_packing/models/common/fixed_orientation_milp.py::add_capacity_strengthening_cuts",
            ),
            ConstraintDefinition(
                "floor_contact", LocalizedText(vi="Tiếp xúc sàn", en="Floor contact"),
                r"f_{ik}\le a_{ik},\quad z_i\le M_z(1-f_{ik})",
                LocalizedText(vi="Biến floor chỉ kích hoạt cho kiện được gán và ép z bằng 0.", en="Floor activation requires assignment and forces z to zero."),
                "src/container_packing/models/level_02/milp_model.py::build_level2_model",
            ),
            ConstraintDefinition(
                "support_top_contact", LocalizedText(vi="Tiếp xúc mặt trên", en="Top-face contact"),
                r"s_{ijkpq}=1\Rightarrow z_i=z_j+h_j",
                LocalizedText(vi="Kiện đỡ và kiện được đỡ tiếp xúc theo chiều cao.", en="The supported item contacts the supporter's top face."),
                "src/container_packing/models/level_02/milp_model.py::_add_contact",
            ),
            ConstraintDefinition(
                "support_grid_coverage", LocalizedText(vi="Tỷ lệ hỗ trợ đáy", en="Base support ratio"),
                r"Gf_{ik}+\sum_{j\ne i,p,q}s_{ijkpq}\ge N_{min}a_{ik}",
                LocalizedText(vi="Sàn hoặc các mặt trên phải hỗ trợ đủ số điểm grid.", en="The floor or top faces must support enough base-grid points."),
                "src/container_packing/models/level_02/milp_model.py::build_level2_model",
            ),
            ConstraintDefinition(
                "base_center_support", LocalizedText(vi="Hỗ trợ tâm đáy", en="Base-center support"),
                r"f_{ik}+\sum_{j\ne i}c_{ijk}\ge a_{ik}",
                LocalizedText(vi="Tâm đáy phải nằm trên sàn hoặc một mặt đỡ.", en="The base center must lie on the floor or a supporting top face."),
                "src/container_packing/models/level_02/milp_model.py::build_level2_model",
            ),
        ),
        inactive_constraints=tuple(LocalizedText(vi=vi, en=en) for vi, en in (
            ("xoay kiện", "rotation"), ("độ bền chịu tải", "load bearing"),
            ("truyền tải trọng", "load transfer"), ("ổn định vật lý đầy đủ", "full physical stability"),
            ("khả năng chồng", "stackability"), ("hàng dễ vỡ", "fragility"),
            ("trọng tâm", "center of gravity"), ("thứ tự xếp/dỡ", "loading/unloading order"),
        )),
        assumptions=_LEVEL_01_CONTRACT.assumptions + (
            LocalizedText(
                vi="Support được xấp xỉ trong MILP bằng grid và được kiểm tra lại bằng diện tích hợp chính xác.",
                en="MILP support uses a grid approximation and is rechecked with exact rectangle-union area.",
            ),
        ),
        limitations=(
            LocalizedText(
                vi="Support hình học không chứng minh ổn định cơ học hoặc khả năng chịu tải.",
                en="Geometric support does not prove mechanical stability or load-bearing capacity.",
            ),
            LocalizedText(
                vi="MILP tăng nhanh theo số kiện, container và độ phân giải grid.",
                en="MILP size grows quickly with items, containers, and grid resolution.",
            ),
        ),
        solution_claim=LocalizedText(
            vi="Nghiệm hợp lệ về hình học, tải trọng và hỗ trợ đáy theo giả định Level 2.",
            en="A geometry, payload, and base-support-feasible solution under Level 2 assumptions.",
        ),
    ),
)


_LEVEL_02_CONTRACT = _LEVELS["level_02"].contract
_LEVELS["level_03"] = LevelDefinition(
    level_id="level_03",
    description="Horizontal item orientation plus Level 2 geometric support constraints",
    default_config=Path("config/level_03/default.yaml"),
    supported_algorithms=(
        "milp_big_m", "extreme_point_ffd", "extreme_point_best_fit", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
        "maximal_space_best_fit",
    ),
    run=level_03.run,
    prepare=level_03.prepare,
    validate_run=level_03.validate_run,
    algorithm_configs={
        "milp_big_m": Path("config/level_03/experiments/milp_big_m_reference.yaml"),
    },
    contract=LevelContract(
        title=LocalizedText(
            vi="Level 3 — Xoay ngang và ràng buộc hỗ trợ hình học",
            en="Level 3 — Horizontal orientation and geometric support",
        ),
        problem=LocalizedText(
            vi="Kế thừa Level 2 và cho phép mỗi kiện giữ nguyên hoặc hoán đổi chiều dài, chiều rộng; chiều cao luôn giữ theo trục đứng.",
            en="Extend Level 2 by allowing each item to keep or swap its horizontal length and width, while height always remains vertical.",
        ),
        notation=_LEVEL_02_CONTRACT.notation + (
            MathematicalExpression(
                "orientation_set",
                LocalizedText(vi="Tập orientation ngang", en="Horizontal orientation set"),
                r"O_i\subseteq\{XYZ,YXZ\},\quad r_{io}\in\{0,1\}",
                LocalizedText(
                    vi="Mỗi kiện dùng profile synthetic để chọn các hướng ngang được phép.",
                    en="Each item uses the declared synthetic profile to select permitted horizontal orientations.",
                ),
                "src/container_packing/algorithms/orientation.py::ProfileOrientationProvider",
            ),
        ),
        objective=_LEVEL_02_CONTRACT.objective,
        variables=_LEVEL_02_CONTRACT.variables + (
            VariableDefinition(
                "r[i,o]", r"r_{io}\in\{0,1\}", LocalizedText(vi="Nhị phân", en="Binary"),
                LocalizedText(vi="kiện i, hướng ngang o", en="item i, horizontal orientation o"),
                LocalizedText(
                    vi="Bằng 1 khi kiện i chọn hướng o; FFD lưu mã chọn trong placement.orientation_code.",
                    en="Equals 1 when item i chooses o; FFD records the choice in placement.orientation_code.",
                ),
                "src/container_packing/algorithms/orientation.py::ProfileOrientationProvider; schemas.py::Placement.orientation_code",
            ),
        ),
        active_constraints=_LEVEL_02_CONTRACT.active_constraints + (
            ConstraintDefinition(
                "horizontal_orientation_selection",
                LocalizedText(vi="Chọn đúng một orientation", en="Select exactly one orientation"),
                r"\sum_{o\in O_i}r_{io}=1\quad\forall i\in I",
                LocalizedText(
                    vi="Mỗi kiện chọn XYZ hoặc YXZ; đáy vuông được khử trùng lặp.",
                    en="Each item selects XYZ or YXZ; duplicate orientations are removed for square bases.",
                ),
                "src/container_packing/geometry/orientation.py::allowed_orientation_codes",
            ),
            ConstraintDefinition(
                "orientation_dependent_dimensions",
                LocalizedText(vi="Kích thước phụ thuộc orientation", en="Orientation-dependent dimensions"),
                r"(\ell'_i,w'_i,h'_i)=\sum_{o\in O_i}(\ell_{io},w_{io},h_{io})r_{io}",
                LocalizedText(
                    vi="Chỉ chiều dài và chiều rộng có thể hoán đổi; chiều cao không đổi.",
                    en="Only length and width may swap; height is unchanged.",
                ),
                "src/container_packing/geometry/orientation.py::oriented_dimensions",
            ),
        ),
        inactive_constraints=tuple(LocalizedText(vi=vi, en=en) for vi, en in (
            ("xoay làm đổi trục đứng", "vertical-axis rotation"),
            ("độ bền chịu tải", "load bearing"), ("truyền tải trọng", "load transfer"),
            ("ổn định vật lý đầy đủ", "full physical stability"), ("khả năng chồng", "stackability"),
            ("lồng kiện", "nesting"), ("hàng dễ vỡ", "fragility"),
            ("trọng tâm", "center of gravity"), ("thứ tự xếp/dỡ", "loading/unloading order"),
        )),
        assumptions=_LEVEL_02_CONTRACT.assumptions + (
            LocalizedText(
                vi="forced_orientation của dữ liệu nguồn chưa có mapping đã xác minh; profile orientation hiện là synthetic và được lưu trong manifest.",
                en="The source forced_orientation field has no verified mapping; the active orientation profile is synthetic and persisted in the manifest.",
            ),
        ),
        limitations=(
            LocalizedText(
                vi="FFD là default thực tế; MILP orientation chỉ là exact reference cho instance nhỏ (tối đa 5 kiện).",
                en="FFD is the practical default; orientation MILP is an exact reference for small instances only (up to 5 items).",
            ),
            LocalizedText(
                vi="Support hình học không chứng minh ổn định cơ học hoặc khả năng chịu tải.",
                en="Geometric support does not prove mechanical stability or load-bearing capacity.",
            ),
        ),
        solution_claim=LocalizedText(
            vi="Nghiệm hợp lệ về hình học, tải trọng, support đáy và xoay ngang theo giả định Level 3.",
            en="A geometry, payload, base-support, and horizontal-orientation-feasible solution under Level 3 assumptions.",
        ),
    ),
)


_LEVEL_03_CONTRACT = _LEVELS["level_03"].contract
_LEVELS["level_04"] = LevelDefinition(
    level_id="level_04",
    description="Horizontal orientation, exact support, and same-code stackability rules",
    default_config=Path("config/level_04/default.yaml"),
    supported_algorithms=(
        "extreme_point_ffd", "extreme_point_best_fit", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
        "maximal_space_best_fit",
    ),
    run=level_04.run,
    prepare=level_04.prepare,
    validate_run=level_04.validate_run,
    contract=LevelContract(
        title=LocalizedText(vi="Level 4 — Quy tắc chồng kiện", en="Level 4 — Stackability rules"),
        problem=LocalizedText(
            vi="Kế thừa Level 3 và chỉ cho phép quan hệ chồng trực tiếp giữa các kiện cùng nhóm stackability.",
            en="Extend Level 3 by allowing declared direct stack relations only for compatible stackability groups.",
        ),
        notation=_LEVEL_03_CONTRACT.notation + (
            MathematicalExpression(
                "stack_parent_relation", LocalizedText(vi="Quan hệ đỡ trực tiếp", en="Direct stack-parent relation"),
                r"p_{jik}\in\{0,1\}",
                LocalizedText(vi="Bằng 1 khi j là parent trực tiếp của i trong container k.", en="Equals one when j is the declared direct parent of i in container k."),
                "src/container_packing/levels/stackability.py::StackParentRelation",
            ),
        ),
        objective=_LEVEL_03_CONTRACT.objective,
        variables=_LEVEL_03_CONTRACT.variables + (
            VariableDefinition(
                "p[j,i,k]", r"p_{jik}\in\{0,1\}", LocalizedText(vi="Nhị phân", en="Binary"),
                LocalizedText(vi="parent j, child i, container k", en="parent j, child i, container k"),
                LocalizedText(vi="Quan hệ stack trực tiếp được khai báo từ nghiệm cuối.", en="Declared direct stack relation reconstructed from the final solution."),
                "src/container_packing/levels/stackability.py::StackParentRelation",
            ),
        ),
        active_constraints=_LEVEL_03_CONTRACT.active_constraints + (
            ConstraintDefinition(
                "stackability_same_group", LocalizedText(vi="Tương thích nhóm stack", en="Same-group stack compatibility"),
                r"p_{jik}=1\Rightarrow g_i=g_j",
                LocalizedText(vi="Parent và child trực tiếp phải có cùng stackability code.", en="Direct parent and child must have the same stackability code."),
                "src/container_packing/levels/level_04_validation.py::_validate_relation",
            ),
            ConstraintDefinition(
                "maximum_stack_layers", LocalizedText(vi="Giới hạn tầng stack", en="Maximum stack layers"),
                r"|\operatorname{chain}(i)|\le\min_{v\in\operatorname{chain}(i)}m_v",
                LocalizedText(vi="Số tầng của chain không vượt cap hiệu lực nhỏ nhất.", en="A parent chain cannot exceed its minimum effective cap."),
                "src/container_packing/levels/level_04_validation.py::_stack_records",
            ),
        ),
        inactive_constraints=tuple(LocalizedText(vi=vi, en=en) for vi, en in (
            ("xoay làm đổi trục đứng", "vertical-axis rotation"), ("chịu tải", "load bearing"),
            ("truyền tải", "load transfer"), ("ổn định vật lý đầy đủ", "full physical stability"),
            ("hàng dễ vỡ", "fragility"), ("trọng tâm", "center of gravity"),
            ("thứ tự xếp/dỡ", "loading/unloading order"), ("lồng kiện", "nesting"),
        )),
        assumptions=_LEVEL_03_CONTRACT.assumptions + (
            LocalizedText(vi="Stackability code tương thích theo equality; max_stackability dùng convention versioned của Level 4.", en="Stackability compatibility uses code equality; max_stackability uses the versioned Level 4 convention."),
        ),
        limitations=(
            LocalizedText(vi="FFD là practical default; chưa có Level 4 MILP reference.", en="FFD is the practical default; no Level 4 MILP reference exists yet."),
            LocalizedText(vi="Không tính tải truyền qua stack hoặc độ bền chịu tải.", en="No stack load transfer or load-bearing capacity is modeled."),
        ),
        solution_claim=LocalizedText(
            vi="Nghiệm hợp lệ về hình học, tải trọng, support, xoay ngang và quy tắc stack theo Level 4.",
            en="A geometry, payload, support, horizontal-orientation, and stackability-feasible solution under Level 4 assumptions.",
        ),
    ),
)


_LEVEL_04_CONTRACT = _LEVELS["level_04"].contract
_LEVELS["level_05"] = LevelDefinition(
    level_id="level_05",
    description=(
        "Level 4 plus static recursive vertical load transfer and "
        "synthetic load-bearing capacities"
    ),
    default_config=Path("config/level_05/default.yaml"),
    supported_algorithms=(
        "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    ),
    run=level_05.run,
    prepare=level_05.prepare,
    validate_run=level_05.validate_run,
    contract=LevelContract(
        title=LocalizedText(
            vi="Level 5 — Khả năng chịu tải và truyền tải trọng tĩnh",
            en="Level 5 — Static load bearing and load transfer",
        ),
        problem=LocalizedText(
            vi=(
                "Kế thừa Level 4, phân phối tải theo diện tích tiếp xúc và "
                "giới hạn tổng tải phía trên mà mỗi kiện có thể chịu."
            ),
            en=(
                "Extend Level 4 by distributing load according to contact area "
                "and limiting the total load carried above each item."
            ),
        ),
        notation=_LEVEL_04_CONTRACT.notation + (
            MathematicalExpression(
                "load_transfer_fraction",
                LocalizedText(vi="Tỷ lệ truyền tải", en="Load-transfer fraction"),
                r"A_{ji}=|\operatorname{contact}(j,i)|,\quad "
                r"\lambda_{ji}=\frac{A_{ji}}{\sum_s A_{si}}",
                LocalizedText(
                    vi="Tải của kiện i được chia cho các kiện j đỡ nó theo diện tích tiếp xúc.",
                    en="Item i's load is split among its supporters j by contact area.",
                ),
                "src/container_packing/levels/load_transfer.py::evaluate_load_transfer",
            ),
        ),
        objective=_LEVEL_04_CONTRACT.objective,
        variables=_LEVEL_04_CONTRACT.variables + (
            VariableDefinition(
                "T[i]",
                r"T_i\in\mathbb{R}_{\ge0}",
                LocalizedText(vi="Đại lượng suy ra liên tục", en="Continuous derived quantity"),
                LocalizedText(vi="kiện i", en="item i"),
                LocalizedText(
                    vi="Tổng tải kiện i truyền xuống, gồm tự trọng và tải nhận từ phía trên.",
                    en="Total load transmitted by item i, including own weight and received load.",
                ),
                "src/container_packing/levels/load_transfer.py::evaluate_load_transfer",
            ),
            VariableDefinition(
                "L[i]",
                r"L_i\in\mathbb{R}_{\ge0}",
                LocalizedText(vi="Đại lượng suy ra liên tục", en="Continuous derived quantity"),
                LocalizedText(vi="kiện i", en="item i"),
                LocalizedText(
                    vi="Tải phía trên mà kiện i đang chịu, không gồm tự trọng.",
                    en="Load carried above item i, excluding its own weight.",
                ),
                "src/container_packing/levels/load_transfer.py::LoadBearingRecord.load_above_kg",
            ),
        ),
        active_constraints=_LEVEL_04_CONTRACT.active_constraints + (
            ConstraintDefinition(
                "recursive_static_load_transfer",
                LocalizedText(vi="Truyền tải tĩnh đệ quy", en="Recursive static load transfer"),
                r"T_i=w_i+\sum_h\lambda_{ih}T_h,\qquad L_i=T_i-w_i",
                LocalizedText(
                    vi="Tải được tính từ trên xuống dưới qua toàn bộ đồ thị tiếp xúc.",
                    en="Load is evaluated top-down over the complete contact graph.",
                ),
                "src/container_packing/levels/load_transfer.py::evaluate_load_transfer",
            ),
            ConstraintDefinition(
                "maximum_supported_weight",
                LocalizedText(vi="Giới hạn chịu tải", en="Load-bearing capacity"),
                r"L_i\le M_i\quad\forall i",
                LocalizedText(
                    vi="Tải phía trên không vượt sức chịu tải khai báo của kiện.",
                    en="Load carried above an item cannot exceed its declared capacity.",
                ),
                "src/container_packing/levels/level_05_validation.py::validate_load_bearing",
            ),
            ConstraintDefinition(
                "fragile_no_supported_load",
                LocalizedText(vi="Kiện dễ vỡ không chịu tải", en="Fragile items carry no load"),
                r"\operatorname{fragile}_i=1\Rightarrow L_i=0",
                LocalizedText(
                    vi="Kiện được đánh dấu dễ vỡ không được có tải phía trên.",
                    en="An item declared fragile must carry no load above it.",
                ),
                "src/container_packing/levels/level_05_validation.py::validate_load_bearing",
            ),
        ),
        inactive_constraints=tuple(
            LocalizedText(vi=vi, en=en)
            for vi, en in (
                ("áp suất tiếp xúc", "contact pressure"),
                ("mô-men và lật", "moments and tipping"),
                ("tải động và rung động", "dynamic and vibration loads"),
                ("cân bằng tải container", "container load balance"),
                ("lồng kiện", "nesting"),
                ("thứ tự xếp/dỡ", "loading/unloading order"),
            )
        ),
        assumptions=_LEVEL_04_CONTRACT.assumptions + (
            LocalizedText(
                vi=(
                    "Sức chịu tải hiện dùng profile nghiên cứu M_i=4w_i nếu "
                    "không có override; đây không phải thông số vật liệu thực."
                ),
                en=(
                    "Load capacity currently uses the research profile M_i=4w_i "
                    "unless overridden; it is not a real material property."
                ),
            ),
            LocalizedText(
                vi="Tải chỉ truyền thẳng đứng và được chia theo diện tích tiếp xúc.",
                en="Load transfers vertically and is split by contact area only.",
            ),
        ),
        limitations=(
            LocalizedText(
                vi="Best Fit là mặc định thực tế; FFD, Hill Climbing và SA là comparator.",
                en="Best Fit is the practical default; FFD, Hill Climbing, and SA are comparators.",
            ),
            LocalizedText(
                vi=(
                    "Mô hình chưa tính áp suất cục bộ, mô-men, biến dạng, tải động "
                    "hoặc độ bền vật liệu thực."
                ),
                en=(
                    "The model omits local pressure, moments, deformation, dynamic "
                    "loads, and real material strength."
                ),
            ),
        ),
        solution_claim=LocalizedText(
            vi=(
                "Nghiệm hợp lệ về hình học, tải trọng container, support, xoay ngang, "
                "stackability và truyền tải tĩnh theo profile nghiên cứu Level 5."
            ),
            en=(
                "A geometry, container-payload, support, horizontal-orientation, "
                "stackability, and static-load-feasible solution under the Level 5 "
                "research profile."
            ),
        ),
    ),
)


_level_05_contract = _LEVELS["level_05"].contract
_level_06_definition = _LEVELS["level_06"]
_level_06_contract = _level_06_definition.contract
_LEVELS["level_06"] = replace(
    _level_06_definition,
    contract=replace(
        _level_06_contract,
        notation=_level_05_contract.notation + _level_06_contract.notation[-1:],
        objective=_level_05_contract.objective,
        variables=_level_05_contract.variables + _level_06_contract.variables[-1:],
        active_constraints=(
            _level_05_contract.active_constraints + _level_06_contract.active_constraints[-2:]
        ),
        inactive_constraints=tuple(
            value for value in _level_05_contract.inactive_constraints if value.en != "nesting"
        ) + _level_06_contract.inactive_constraints[-3:],
        assumptions=_level_05_contract.assumptions + _level_06_contract.assumptions[-1:],
    ),
)

_LEVELS["level_07"] = LevelDefinition(
    level_id="level_07",
    description="Experimental center-of-mass balance runtime with controlled fixtures and arbitrary-input constructive solvers",
    default_config=Path("config/level_07/default.yaml"),
    supported_algorithms=(
        "extreme_point_best_fit_balance",
        "extreme_point_ffd_balance",
        "level_07_fixture_validation_bundle",
        "extreme_point_best_fit_balance_fixture",
        "extreme_point_best_fit_balance_baseline_fixture",
        "extreme_point_ffd_balance_fixture",
        "extreme_point_ffd_balance_baseline_fixture",
    ),
    run=level_07.run,
    prepare=level_07.prepare,
    validate_run=level_07.validate_run,
    web_visible=True,
    algorithm_configs={
        "extreme_point_best_fit_balance": Path("config/level_07/default.yaml"),
        "extreme_point_ffd_balance": Path("config/level_07/experiments/fast.yaml"),
        "level_07_fixture_validation_bundle": Path("config/level_07/experimental.yaml"),
        "extreme_point_best_fit_balance_fixture": Path("config/level_07/experiments/balance_aware_best_fit_fixture.yaml"),
        "extreme_point_best_fit_balance_baseline_fixture": Path("config/level_07/experiments/balance_baseline_best_fit_fixture.yaml"),
        "extreme_point_ffd_balance_fixture": Path("config/level_07/experiments/ffd_balance_aware_fixture.yaml"),
        "extreme_point_ffd_balance_baseline_fixture": Path("config/level_07/experiments/ffd_balance_baseline_fixture.yaml"),
    },
    contract=replace(
        _LEVELS["level_06"].contract,
        title=LocalizedText(
            vi="Level 7 — Trọng tâm và cân bằng (fixture CLI)",
            en="Level 7 — Center of mass and balance (experimental)",
        ),
        problem=LocalizedText(
            vi="Xác minh fixture compound-root đã khóa theo trọng tâm khối lượng; không tối ưu hóa packing.",
            en="Pack compound roots with per-container center-of-mass balance and independently validate every inherited constraint.",
        ),
        notation=_LEVELS["level_06"].contract.notation + (
            MathematicalExpression(
                "center_of_mass",
                LocalizedText(vi="Trọng tâm container", en="Container center of mass"),
                r"X_k^{cg}=\frac{\sum_{i\in k}q_i(x_i+\ell_i/2)}{\sum_{i\in k}q_i},\quad Y_k^{cg}=\frac{\sum_{i\in k}q_i(y_i+w_i/2)}{\sum_{i\in k}q_i}",
                LocalizedText(
                    vi="Tính lại độc lập từ compound-root placements và khối lượng.",
                    en="Recomputed independently from compound-root placements and masses.",
                ),
                "src/container_packing/levels/center_of_mass.py::evaluate_center_of_mass",
            ),
        ),
        objective=MathematicalExpression(
            "validation_only",
            LocalizedText(vi="Không có hàm mục tiêu solver", en="No solver objective"),
            r"\text{validation only}",
            LocalizedText(
                vi="Runtime chỉ tạo bằng chứng fixture, không tìm phương án xếp.",
                en="The runtime produces fixture evidence only and does not search for a packing solution.",
            ),
            "src/container_packing/levels/level_07.py::run",
        ),
        active_constraints=_LEVELS["level_06"].contract.active_constraints + (
            ConstraintDefinition(
                "compound_root_center_of_mass_balance",
                LocalizedText(vi="Cân bằng trọng tâm", en="Center-of-mass balance"),
                r"|X_k^{cg}/L_k-t_k^x|\le\tau_k^x,\quad |Y_k^{cg}/W_k-t_k^y|\le\tau_k^y",
                LocalizedText(
                    vi="Kiểm tra ngưỡng dải cân bằng dọc và ngang cho fixture đã khóa.",
                    en="Checks longitudinal and lateral balance bands for the frozen fixture.",
                ),
                "src/container_packing/levels/level_07_validation.py::validate_container_balance",
            ),
        ),
        inactive_constraints=_LEVELS["level_06"].contract.inactive_constraints + (
            LocalizedText(vi="solver cân bằng thực tế", en="practical balance-aware solver"),
            LocalizedText(vi="tải theo vùng sàn", en="floor-zone load limits"),
            LocalizedText(vi="khoảng trống cửa", en="door clearance"),
            LocalizedText(vi="giới hạn tải trục", en="axle load limits"),
        ),
        assumptions=_LEVELS["level_06"].contract.assumptions + (
            LocalizedText(
                vi="Chỉ chấp nhận fixture prefix 4 kiện/1 container, hướng XYZ và môi trường local.",
                en="Accepts only the prefix 4-item/1-container fixture, XYZ orientation, and local environment.",
            ),
        ),
        limitations=_LEVELS["level_06"].contract.limitations + (
            LocalizedText(
                vi="VALIDATION_ONLY không phải nghiệm tối ưu hay solver packing thực tế.",
                en="VALIDATION_ONLY is neither an optimal solution nor a practical packing solver.",
            ),
        ),
        solution_claim=LocalizedText(
            vi="Bằng chứng fixture được kiểm định độc lập cho Level 6 và ngưỡng cân bằng Level 7.",
            en="Independently validated fixture evidence for Level 6 and Level 7 balance bands.",
        ),
    ),
)

# The original acceptance-fixture contract remains documented above for its
# regression algorithms.  The registered experimental runtime inherits the
# Level 6 objective and adds balance as final validation plus a construction
# tie-break for its web-visible algorithms.
_level_07_definition = _LEVELS["level_07"]
_LEVELS["level_07"] = replace(
    _level_07_definition,
    contract=replace(
        _level_07_definition.contract,
        title=LocalizedText(
            vi="Level 7 — Trọng tâm và cân bằng tải (thực nghiệm)",
            en="Level 7 — Center of mass and balance (experimental)",
        ),
        problem=LocalizedText(
            vi="Xếp compound root với cân bằng trọng tâm theo từng container, rồi kiểm định độc lập toàn bộ ràng buộc kế thừa.",
            en="Pack compound roots with per-container center-of-mass balance and independently validate every inherited constraint.",
        ),
        objective=_LEVELS["level_06"].contract.objective,
        assumptions=_level_07_definition.contract.assumptions[:-1] + (
            LocalizedText(
                vi="Cân bằng là kiểm định cứng cuối cùng và tie-break mềm khi dựng nghiệm; COG tạm thời lệch không tự loại placement.",
                en="Balance is a hard final validation and a soft construction tie-break; temporary COG deviation does not itself prune a placement.",
            ),
        ),
        limitations=_level_07_definition.contract.limitations[:-1] + (
            LocalizedText(
                vi="Best Fit và FFD mới ở mức thực nghiệm; chưa có tải trục, tải vùng sàn, khoảng trống cửa, mô-men hay chứng nhận vận tải.",
                en="Best Fit and FFD remain experimental; axle loads, floor zones, door clearance, moments, and transport certification are inactive.",
            ),
        ),
        solution_claim=LocalizedText(
            vi="Nghiệm hình học, nesting, support, stackability, chịu tải và cân bằng trọng tâm đều được kiểm định độc lập.",
            en="Geometry, nesting, support, stackability, load-bearing, and center-of-mass balance are independently validated.",
        ),
    ),
)

_level_08_base = _LEVELS["level_07"].contract
_LEVELS["level_08"] = LevelDefinition(
    level_id="level_08",
    description="Experimental delivery-aware packing with static LIFO validation over inherited Level 1–7 evidence",
    default_config=Path("config/level_08/default.yaml"),
    supported_algorithms=(
        "level_08_fixture_validation_bundle",
        "extreme_point_best_fit_delivery_baseline_fixture",
        "extreme_point_best_fit_delivery_aware_fixture",
        "extreme_point_ffd_delivery_negative_control_fixture",
        "extreme_point_ffd_delivery_aware_fixture",
        "level_08_sequential_replay_fixture",
        "extreme_point_best_fit_delivery",
        "extreme_point_ffd_delivery",
    ),
    run=level_08.run,
    prepare=level_08.prepare,
    validate_run=level_08.validate_run,
    web_visible=True,
    algorithm_configs={
        "level_08_fixture_validation_bundle": Path("config/level_08/runtime_candidate.yaml"),
        "extreme_point_best_fit_delivery_baseline_fixture": Path("config/level_08/experiments/delivery_best_fit_baseline_fixture.yaml"),
        "extreme_point_best_fit_delivery_aware_fixture": Path("config/level_08/experiments/delivery_best_fit_aware_fixture.yaml"),
        "extreme_point_ffd_delivery_negative_control_fixture": Path("config/level_08/experiments/ffd_multi_container_negative_control_fixture.yaml"),
        "extreme_point_ffd_delivery_aware_fixture": Path("config/level_08/experiments/ffd_delivery_aware_fixture.yaml"),
        "level_08_sequential_replay_fixture": Path("config/level_08/experiments/sequential_replay_fixture.yaml"),
        "extreme_point_best_fit_delivery": Path("config/level_08/default.yaml"),
        "extreme_point_ffd_delivery": Path("config/level_08/experiments/ffd_delivery_local.yaml"),
    },
    contract=replace(
        _level_08_base,
        title=LocalizedText(
            vi="Level 8 — Thứ tự giao và tháo dỡ LIFO (thực nghiệm)",
            en="Level 8 — Delivery order and LIFO unloading (experimental)",
        ),
        problem=LocalizedText(
            vi="Xếp kiện theo ưu tiên giao hàng và kiểm định độc lập khả năng tháo thẳng qua cửa, sau toàn bộ ràng buộc Level 1–7.",
            en="Pack items with delivery priorities and independently validate straight-path unloadability after every Level 1–7 constraint.",
        ),
        objective=_level_08_base.objective,
        active_constraints=_level_08_base.active_constraints + (
            ConstraintDefinition(
                "static_lifo_unloadability",
                LocalizedText(vi="Tháo dỡ LIFO tĩnh", en="Static LIFO unloadability"),
                r"p_j>p_i \land j\in B_i \Rightarrow \text{rehandle}_{ji}=1",
                LocalizedText(vi="Kiện giao muộn chắn đường thẳng của kiện giao sớm là vi phạm LIFO.", en="A later-delivery item blocking an earlier item's straight path is a LIFO violation."),
                "src/container_packing/levels/level_08_validation.py::validate_unloading_lifo",
            ),
        ),
        inactive_constraints=_level_08_base.inactive_constraints + (
            LocalizedText(vi="chuỗi tháo dỡ chính xác", en="exact removal sequence"),
            LocalizedText(vi="thiết bị và vùng chứa tạm", en="handling equipment and staging"),
        ),
        assumptions=_level_08_base.assumptions + (
            LocalizedText(vi="Cửa ở x_min và tháo theo đường thẳng -x; priority nhỏ được giao trước.", en="The door is at x_min with straight -x removal; lower priority is delivered earlier."),
        ),
        limitations=_level_08_base.limitations + (
            LocalizedText(vi="Best Fit và FFD là solver thực nghiệm; mô hình chỉ kiểm tra tháo thẳng tĩnh, chưa có chuỗi thao tác hoặc mô phỏng dỡ hàng vật lý.", en="Best Fit and FFD are experimental solvers; the model checks static straight-path unloading only, without an exact operation sequence or physical handling simulation."),
        ),
        solution_claim=LocalizedText(
            vi="Nghiệm được kiểm định độc lập về hình học, tải trọng, support, stackability, chịu tải, cân bằng trọng tâm và LIFO tĩnh từ Level 1 đến Level 8.",
            en="The solution is independently validated for geometry, payload, support, stackability, load-bearing, center-of-mass balance, and static LIFO from Level 1 through Level 8.",
        ),
    ),
)


def list_levels() -> tuple[LevelDefinition, ...]:
    return tuple(_LEVELS[key] for key in sorted(_LEVELS))


def get_level(level_id: str) -> LevelDefinition:
    try:
        return _LEVELS[level_id]
    except KeyError as exc:
        available = ", ".join(sorted(_LEVELS))
        raise ValueError(f"Level {level_id!r} is not implemented. Available: {available}") from exc
