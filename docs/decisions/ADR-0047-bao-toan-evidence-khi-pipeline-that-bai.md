# ADR-0047 — Bảo toàn evidence khi pipeline thất bại

## Trạng thái

Accepted — 2026-08-20.

## Bối cảnh

Một execution có thể hoàn thành construction nhưng lỗi ở bước ghi CSV/JSON hoặc
reporting. Trước đây benchmark runner bắt exception rồi thay toàn bộ metadata bằng
dictionary rỗng. Một lỗi thứ cấp như thiếu `n_items` vì vậy có thể che mất trạng
thái solver, lý do dừng, số kiện đã xếp và quy mô input đã resolve.

Điều này làm người đọc dễ hiểu nhầm lỗi xuất báo cáo là solver không tìm được
nghiệm, đồng thời làm recovery thiếu căn cứ để chọn đúng execution cần chạy lại.

## Quyết định

- Pipeline tạo context đầu vào authoritative ngay sau khi load dữ liệu, gồm số
  kiện đã chọn và toàn bộ physical container inventory.
- Exception ở construction, independent validation, reporting và post-write được
  bọc bằng `ExperimentExecutionError`, kèm snapshot metadata tại thời điểm lỗi.
- Failure row luôn có `failure_class`, `failure_stage`, loại/lời nhắn lỗi và lý do
  dừng canonical nếu đã tồn tại.
- Nếu computation đã có status hoặc objective trước khi reporting lỗi, giá trị đó
  chỉ được giữ dưới dạng diagnostic. Status cuối là `ERROR`; official objective và
  secondary score bắt buộc là `null`.
- `metrics_payload` không được phát sinh `KeyError` khi evidence chưa đầy đủ. Nó
  ghi rõ trường nào còn thiếu để điều tra, thay vì tự bịa số liệu.
- Independent validator và solver contract không thay đổi.

## Hệ quả

- Reporting failure không còn bị trình bày như bằng chứng bài toán infeasible.
- Corpus/recovery runner giữ được input cardinality và termination reason gốc.
- Artifact lịch sử vẫn đọc được; các trường mới là additive và không rewrite
  output cũ.
- Failure trước khi input được resolve không được gán giả `n_items` hoặc physical
  inventory; request count vẫn được giữ riêng nếu có.

## Giới hạn

Quyết định này tăng độ tin cậy của evidence, không sửa heuristic, không làm một
nghiệm invalid thành valid và không tự recovery execution thất bại.
