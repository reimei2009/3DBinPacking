# ADR-0041 — Validated incumbent và objective chính thức

## Trạng thái

Accepted cho core Level 1–2.

## Bối cảnh

Inventory consolidation từng có một nhánh full rebuild thay incumbent chỉ dựa
trên trạng thái `FEASIBLE` và số container. Nhánh đó chưa gọi independent
validator, nên một candidate ít container nhưng sai contract level có thể làm
mất baseline hợp lệ. Scalar objective cũ còn phụ thuộc tổng chi phí của toàn
catalog, vì vậy không phù hợp để xếp hạng chéo giữa hai catalog.

## Quyết định

- Objective chính thức là tuple `(số container đã dùng, tổng chi phí container)`.
- Scalar mã hóa cũ được giữ dưới tên `encoded_solver_objective` chỉ để tương
  thích artifact lịch sử.
- `ValidatedIncumbentStore` là cửa duy nhất để construction/repair thay incumbent.
- Candidate phải complete, có status thành công, tốt hơn theo tuple và qua
  independent validator của level.
- Repair timeout, hết budget hoặc tạo candidate invalid luôn trả lại validated
  incumbent gần nhất.
- Pipeline vẫn validate lại nghiệm cuối từ input gốc; validation trung gian
  không được tái sử dụng làm bằng chứng cuối.
- Nghiệm incomplete, timeout hoặc invalid luôn có objective chính thức `null`.

## Hệ quả

Validation chỉ chạy cho candidate có khả năng cải thiện objective, tránh chi phí
không cần thiết. Level 2 tiếp tục dùng support closure để không tách supporter và
dependent khi relocation/partial repack. Hill Climbing và Simulated Annealing
vẫn là comparator riêng, không trở thành inventory repair canonical.
