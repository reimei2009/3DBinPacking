# Mục lục tài liệu

Đây là điểm bắt đầu canonical cho tài liệu dự án. Runtime registry quyết định
khả năng thực thi; `config/common/capability_matrix.yaml` quyết định cách phân
loại maturity, vai trò và exposure.

Tài liệu trình bày tổng hợp hiện tại:
[WIP 4 tuần — Tech doc và kịch bản demo](reports/manual/wip_04_technical_demo_20260815.md).

## Contract theo level

| Level | Contract canonical | Trạng thái |
| --- | --- | --- |
| 1 | [Hình học và tải trọng](levels/level_01.md) | Nghiên cứu đã nghiệm thu |
| 2 | [Geometric support](levels/level_02.md) | Nghiên cứu đã nghiệm thu |
| 3 | [Xoay ngang](levels/level_03.md) | Nghiên cứu đã nghiệm thu |
| 4 | [Stackability](levels/level_04.md) | Nghiên cứu đã nghiệm thu |
| 5 | [Load-bearing](levels/level_05.md) | Nghiên cứu đã nghiệm thu |
| 6 | [Nesting tường minh](levels/level_06.md) | Thử nghiệm |
| 7 | [Trọng tâm và cân bằng](levels/level_07.md) | Thử nghiệm |
| 8 | [Delivery/LIFO/replay](levels/level_08.md) | Thử nghiệm |

## Kiến trúc và quy trình

- [Quản trị tài liệu](design/documentation_governance.md)
- [Cấu trúc project](design/folder_structure.md)
- [Luồng solver và dữ liệu](design/solver_design.md)
- [Thiết kế benchmark](design/benchmark_design.md)
- [Benchmark chuẩn Level 2](benchmarks/level_02_benchmark_v2.md)
- [Profiling runtime Benchmark V2 Level 2](benchmarks/level_02_runtime_profiling.md)
- [A/B repair UI Level 3](benchmarks/level_03_repair_ui_ab.md)
- [Evidence repair UI Level 3 ngày 2026-08-17](reports/manual/level_03_repair_ui_acceptance_20260817.md)
- [Evidence canonical Level 2 ngày 2026-08-13](reports/manual/level_02_canonical_benchmark_20260813.md)
- [Corpus nghiên cứu Level 1](benchmarks/level1_research_corpus.md)
- [Corpus MPV fixed-orientation Level 2](datasets/mpv_fixed_orientation_level2.md)
- [Parameter sweep](design/parameter_sweep_design.md)
- [Kiến trúc Streamlit/Plotly](design/visualization_web_architecture.md)
- [Git workflow](design/git_workflow.md)

## Hướng dẫn vận hành

- [Chạy và kiểm thử thủ công](guides/manual_test_flow.md)
- [Chạy Streamlit](guides/running_web_app.md)
- [Deploy Render](guides/deploy_render.md)
- [Cài đặt Windows](guides/setup_windows.md)
- [Cài đặt Linux](guides/setup_linux.md)
- [Xử lý lỗi](guides/debugging.md)

## Đặc tả chi tiết

Các thư mục `specs/level1` đến `specs/level7` chứa data contract, mô hình toán
hoặc acceptance chi tiết. Nếu trạng thái trong spec mâu thuẫn với tài liệu
`levels/level_XX.md`, tài liệu level và runtime registry là nguồn ưu tiên.

## Quyết định và bằng chứng

- `decisions/`: ADR — lịch sử quyết định, không xóa chỉ vì đã cũ; dùng
  `superseded_by` khi bị thay thế.
- `reports/generated/`: evidence được sinh từ acceptance pipeline.
- `reports/manual/`: baseline/milestone đã tổng hợp từ tác vụ chạy thủ công.
- `algorithms/`: mô tả thuật toán và giới hạn, không phải nguồn maturity.
- `datasets/`: nguồn dữ liệu, transformation và provenance.

Không dùng output lịch sử trong `outputs/` làm tài liệu canonical hoặc hidden
input cho experiment mới.

Baseline R&D đang hiệu lực:

- [Level 2 — nghiệm thu 2026-08-12](reports/manual/level_02_acceptance_20260812.md)
- [Level 2 — acceptance hardening 2026-08-10 (lịch sử)](reports/manual/level_02_acceptance_20260810.md)
- [Level 7 — scale/balance](reports/manual/level_07_scale_baseline.md)
- [Level 8 — sequential replay scale](reports/manual/level_08_sequential_scale_baseline.md)
