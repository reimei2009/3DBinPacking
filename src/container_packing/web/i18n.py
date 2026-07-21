"""Small explicit translation catalog for the replaceable research UI."""

from __future__ import annotations

_TEXT = {
    "page_title": {"vi": "Mô phỏng xếp container 3D", "en": "3D Container Packing R&D"},
    "title": {"vi": "Mô phỏng xếp container 3D — Nghiên cứu", "en": "3D Container Packing — Research Console"},
    "caption": {"vi": "Giao diện dùng chung pipeline với CLI và notebook; không chứa logic solver.", "en": "A thin UI over the same registry-driven pipeline used by CLI and notebooks."},
    "language": {"vi": "Ngôn ngữ", "en": "Language"},
    "level": {"vi": "Cấp độ", "en": "Level"},
    "algorithm": {"vi": "Thuật toán", "en": "Algorithm"},
    "items": {"vi": "Số lượng kiện", "en": "Number of items"},
    "containers": {"vi": "Số lượng container", "en": "Number of containers"},
    "seed": {"vi": "Hạt giống ngẫu nhiên", "en": "Random seed"},
    "environment": {"vi": "Môi trường thực thi", "en": "Environment metadata"},
    "run": {"vi": "Chạy thí nghiệm", "en": "Run experiment"},
    "running": {"vi": "Đang chuẩn bị dữ liệu, giải và kiểm định độc lập...", "en": "Preparing data, solving, and independently validating..."},
    "success": {"vi": "Thí nghiệm hoàn tất và đã qua kiểm định độc lập.", "en": "Experiment completed and passed independent validation."},
    "result_tab": {"vi": "Kết quả và 3D", "en": "Result & 3D"},
    "contract_tab": {"vi": "Mô hình toán học", "en": "Mathematical model"},
    "history_tab": {"vi": "Lịch sử chạy", "en": "Run history"},
    "start_hint": {"vi": "Chọn tham số ở thanh bên và nhấn Chạy thí nghiệm.", "en": "Choose the experiment inputs in the sidebar and click Run experiment."},
    "problem": {"vi": "Bài toán", "en": "Problem"},
    "notation": {"vi": "Ký hiệu và tham số", "en": "Notation and parameters"},
    "objective": {"vi": "Hàm mục tiêu", "en": "Objective function"},
    "variables": {"vi": "Biến quyết định", "en": "Decision variables"},
    "constraints": {"vi": "Các ràng buộc đang hoạt động", "en": "Active constraints"},
    "assumptions": {"vi": "Giả định", "en": "Assumptions"},
    "inactive": {"vi": "Chưa hoạt động trong level này", "en": "Inactive in this level"},
    "code_mapping": {"vi": "Ánh xạ code", "en": "Code mapping"},
    "milp_note": {"vi": "Các công thức dưới đây mô tả mô hình MILP chính xác. Heuristic và metaheuristic không dựng toàn bộ hệ biến này; chúng tạo nghiệm ứng viên rồi dùng cùng validator Level 1.", "en": "The formulas below describe the exact MILP. Heuristics and metaheuristics do not build this full variable system; they construct candidates and use the same Level 1 validator."},
    "status": {"vi": "Trạng thái", "en": "Status"},
    "validation": {"vi": "Kiểm định", "en": "Validation"},
    "items_metric": {"vi": "Số kiện", "en": "Items"},
    "containers_used": {"vi": "Container đã dùng", "en": "Containers used"},
    "objective_metric": {"vi": "Mục tiêu", "en": "Objective"},
    "runtime": {"vi": "Thời gian (giây)", "en": "Runtime (s)"},
    "view": {"vi": "Chế độ xem 3D", "en": "3D view"},
    "all_containers": {"vi": "Tất cả container đã dùng", "en": "All used containers"},
    "show_labels": {"vi": "Hiện nhãn kiện", "en": "Show item labels"},
    "show_boundaries": {"vi": "Hiện khung container", "en": "Show container boundaries"},
    "display_controls": {"vi": "Điều khiển hiển thị 3D", "en": "3D display controls"},
    "display_mode": {"vi": "Chế độ hiển thị", "en": "Display mode"},
    "mode_solid": {"vi": "Rõ khối", "en": "Solid"},
    "mode_balanced": {"vi": "Cân bằng", "en": "Balanced"},
    "mode_xray": {"vi": "X-Ray", "en": "X-Ray"},
    "opacity": {"vi": "Độ đục của kiện", "en": "Item opacity"},
    "selected_item": {"vi": "Làm nổi bật kiện", "en": "Highlight item"},
    "no_selection": {"vi": "Không chọn", "en": "None"},
    "hidden_items": {"vi": "Ẩn các kiện", "en": "Hide items"},
    "selected_details": {"vi": "Thông tin kiện được chọn", "en": "Selected item details"},
    "position": {"vi": "Tọa độ", "en": "Position"},
    "dimensions": {"vi": "Kích thước", "en": "Dimensions"},
    "weight": {"vi": "Khối lượng", "en": "Weight"},
    "utilization": {"vi": "Mức sử dụng container", "en": "Container utilization"},
    "placements": {"vi": "Tọa độ xếp kiện", "en": "Placements"},
    "no_scene": {"vi": "Run này không có scene hợp lệ để hiển thị.", "en": "This run has no valid visualization scene."},
    "no_runs": {"vi": "Chưa có run nào được lưu cho level này.", "en": "No persisted runs exist for this level yet."},
    "persisted_run": {"vi": "Run đã lưu", "en": "Persisted run"},
    "open_run": {"vi": "Mở run đã chọn", "en": "Open selected run"},
    "subset_limit": {"vi": "Giới hạn liệt kê tập container", "en": "Container subset enumeration limit"},
    "time_limit": {"vi": "Giới hạn thời gian MILP (giây)", "en": "MILP time limit (seconds)"},
    "mip_gap": {"vi": "Sai số tương đối MILP", "en": "MILP relative gap"},
    "hill_iterations": {"vi": "Số vòng lặp Hill Climbing", "en": "Hill-climbing iterations"},
    "neighbors": {"vi": "Số nghiệm lân cận mỗi vòng", "en": "Neighbors per iteration"},
    "annealing_iterations": {"vi": "Số vòng lặp Simulated Annealing", "en": "Annealing iterations"},
    "temperature": {"vi": "Nhiệt độ ban đầu", "en": "Initial temperature"},
    "cooling": {"vi": "Tốc độ làm nguội", "en": "Cooling rate"},
}


def text(key: str, language: str) -> str:
    try:
        return _TEXT[key][language]
    except KeyError as exc:
        raise KeyError(f"Missing UI translation for {key!r}/{language!r}") from exc


_FAMILIES = {
    "constructive_heuristic": {"vi": "heuristic kiến tạo", "en": "constructive heuristic"},
    "local_search": {"vi": "tìm kiếm cục bộ", "en": "local search"},
    "metaheuristic": {"vi": "metaheuristic", "en": "metaheuristic"},
    "exact_milp": {"vi": "MILP chính xác", "en": "exact MILP"},
}


def algorithm_family(family: str, language: str) -> str:
    return _FAMILIES.get(family, {}).get(language, family)
