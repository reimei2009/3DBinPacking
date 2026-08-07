# ADR-0039 — Precheck theo giới hạn, incumbent improvement và chẩn đoán thất bại

## Trạng thái

Được chấp nhận.

## Bối cảnh

Inventory search trước đây kiểm tra capacity của toàn kho, nhưng có thể vẫn gọi
constructive solver khi giới hạn tối đa `N` container chắc chắn không đủ. Khi
tìm được nghiệm complete đầu tiên, pipeline cũng chỉ dành một pha consolidation
nhỏ để giảm container. CLI và Streamlit hiển thị trạng thái thất bại nhưng chưa
giải thích nhất quán nguyên nhân và hành động tiếp theo.

## Quyết định

- Thực hiện capacity precheck trên chính `max_used_container_count`. Thiếu volume
  hoặc payload trong giới hạn này là bất khả thi có chứng minh và dừng trước
  construction.
- Kết quả precheck đạt chỉ là điều kiện cần aggregate, không chứng minh khả thi
  hình học.
- Nghiệm complete đầu tiên là incumbent. Pha improvement dùng budget riêng và
  thử các cardinality từ incumbent xuống capacity lower bound.
- Chỉ thay incumbent khi giảm số container hoặc giữ số container nhưng giảm chi
  phí. Utilization chỉ là evidence/tie-break, không thay objective chính thức.
- Search phát sinh reason code/evidence; application formatter dùng cùng dữ liệu
  để diễn giải trên CLI và Streamlit.
- Timeout, candidate-budget exhaustion và heuristic failure không được mô tả là
  chứng minh bài toán vô nghiệm.

## Hệ quả

Run bất khả thi do capacity kết thúc nhanh và có số liệu deficit rõ ràng. Run có
incumbent hợp lệ không bị mất khi improvement timeout. Search vẫn là heuristic
bounded và capacity lower bound không phải nghiệm tối ưu hay chứng minh khả thi
3D.
