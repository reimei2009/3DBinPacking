# ADR-0029 — Nền tảng contract cho time-bounded search

## Trạng thái

Đã chấp thuận cho checkpoint nền tảng. Checkpoint này chưa kích hoạt anytime
scheduler, inventory-wide selection hoặc bounded repair.

## Bối cảnh

Extreme Point FFD và Best Fit trước đây trả về `list[Placement]` khi xếp đủ và
`None` khi một item không còn vị trí hợp lệ. Giá trị `None` làm mất partial
placements, item gây thất bại và lý do dừng. Điều này cản trở việc xây dựng
solver có giới hạn thời gian, incumbent và failure diagnostics.

Project đã có geometry core, feasibility policy và independent validator dùng
chung cho nhiều level. Vì vậy không tạo solver tree mới và không viết lại các
validator hiện hữu.

## Quyết định

Mỗi constructive attempt trả `ConstructionAttemptResult`, gồm:

- cờ `complete`;
- placements đã tạo trong đúng attempt;
- danh sách item chưa được xếp;
- item đầu tiên gây thất bại;
- termination reason;
- deterministic attempt signature;
- bộ đếm candidate cục bộ.

Partial placements chỉ được dùng cho diagnostic và repair trong tương lai.
Chúng không được xuất như nghiệm `FEASIBLE` và không có official objective.

`ConstructiveSearchResult.placements` tiếp tục chỉ trả danh sách placements khi
attempt hoàn chỉnh. Nhờ đó API solver bên ngoài và contract nghiệm hiện tại
được bảo toàn.

Các contract `SearchBudget` và `ValidatedIncumbent` cũng được định nghĩa tại
checkpoint này, nhưng chưa được nối vào orchestration chính. Clock của
`SearchBudget` có thể inject để kiểm thử deadline mà không dùng `sleep`.

## Tương thích

- FFD vẫn giữ First Fit semantics.
- Best Fit vẫn giữ candidate score hiện tại.
- Subset và container-order search chưa thay đổi.
- Objective Level 1–5 chưa thay đổi.
- MILP và independent validator chưa thay đổi.
- Các extension có thể đọc attempt như một sequence placements trong giai đoạn
  migration, nhưng phải dùng `complete` làm nguồn sự thật.

## Hệ quả

Checkpoint sau có thể xây inventory semantics và anytime scheduler mà không
dùng `None` để biểu diễn nhiều loại failure khác nhau. Rejection reason chi tiết
theo từng constraint chưa được triển khai; checkpoint hiện tại chỉ ghi tổng số
candidate đã thử và reason `NO_FEASIBLE_CANDIDATE` hoặc `TIME_LIMIT_REACHED`.

## Giới hạn

- Chưa ghi `unpacked_items.csv` hoặc attempt history ra run directory.
- Chưa có fast incumbent và improvement phase.
- Chưa thay đổi ý nghĩa trường số lượng container trên CLI/UI.
- Chưa có bounded repair.
- Chưa tuyên bố heuristic failure là chứng minh vô nghiệm.
