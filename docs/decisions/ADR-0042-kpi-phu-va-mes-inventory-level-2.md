# ADR-0042 — KPI phụ và MES trong inventory search Level 2

## Trạng thái

Accepted cho thí nghiệm CLI/benchmark Level 1–2; mặc định tắt.

## Bối cảnh

Objective chính thức của project là tuple lexicographic:

```text
(số container đã dùng, tổng chi phí container)
```

MPV gốc tối thiểu hóa số bin đồng nhất. Project có thêm catalog container không
đồng nhất và chi phí, nên một tổng có trọng số kiểu `α/β/γ/δ` không thể thay thế
objective trên mà không làm thay đổi contract toán học và khiến kết quả phụ
thuộc cách hiệu chỉnh hệ số. Tuy nhiên, khi hai candidate có cùng objective
chính thức, các KPI về tập trung sử dụng tài nguyên, khoảng rỗng nội bộ và biên
hỗ trợ vẫn hữu ích để chọn nghiệm dễ diễn giải hơn.

Maximal Empty Spaces (MES) đã là constructive comparator canonical nhưng trước
đây chưa nhận subset policy, deadline và seeded placements của inventory repair.
Tạo một MES inventory implementation thứ hai sẽ gây trùng logic và khó bảo trì.

## Quyết định

- Giữ objective chính thức không đổi.
- Thêm `SecondarySearchScore`, giá trị nhỏ hơn tốt hơn:

  ```text
  (-utilization_concentration,
   internal_void_ratio,
   -minimum_support_margin,
   placement_signature)
  ```

- Chỉ tính score chính thức sau khi candidate complete và qua independent
  validator. `ValidatedIncumbentStore` chỉ dùng score này khi objective chính
  thức bằng nhau.
- Level 1 giữ thành phần support trung tính; Level 2 tính biên exact support so
  với threshold đang hoạt động. Support violation luôn là hard failure.
- Mở rộng MES canonical để nhận shared subset policy, item order, global
  deadline và seeded placements. Seed được dựng lại deterministic và fail-closed
  khi ngoài subset, trùng item hoặc không qua feasibility policy.
- MES dùng cùng `InventorySearchOrchestrator` và
  `BoundedInventoryConsolidator`; không tạo repair engine mới.
- KPI phụ và MES inventory chỉ được nghiệm thu qua CLI/benchmark trong
  checkpoint này. UI không thêm control mới.

## Hệ quả

Official objective luôn thắng mọi cải thiện KPI. Khi KPI tắt, EP và MES giữ
construction score cũ. Khi bật, runtime có thể tăng do hoàn thành bounded
item-order portfolio tại cardinality đầu tiên đã có incumbent; vì vậy config
mặc định vẫn tắt và benchmark phải báo riêng runtime/KPI.

MES tiếp tục là research comparator cho tới khi đạt promotion gate về validity,
determinism, objective và runtime. Hill Climbing/Simulated Annealing không được
port vào inventory pipeline trong quyết định này.

## Tham chiếu

- Martello, Pisinger và Vigo, bài toán 3D-BPP:
  <https://pubsonline.informs.org/doi/10.1287/opre.48.2.256.12386>
- [ADR-0041 — Validated incumbent và objective chính thức](ADR-0041-validated-incumbent-and-official-objective.md)
