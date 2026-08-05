# ADR-0031: Kích hoạt có kiểm soát inventory-aware search cho Level 1

## Trạng thái

Đã chấp nhận dưới dạng opt-in cho Level 1.

## Bối cảnh

Semantics legacy của `container_count=1` chuẩn bị container đầu tiên trong catalog.
Nó không trả lời câu hỏi thực tế hơn: trong toàn bộ kho, physical container nào có
thể chứa tập kiện với số lượng sử dụng và chi phí thấp nhất.

Nền tảng inventory normalization, hard precheck, lower bound và lazy subset search
đã được kiểm thử độc lập tại ADR-0030. Việc promotion cần tránh thay đổi âm thầm
kết quả cũ.

## Quyết định

- `container_search.enabled=false` là mặc định và giữ nguyên pipeline legacy.
- Khi bật, Level 1 chuẩn bị toàn bộ catalog nhưng giữ riêng
  `requested_used_container_count`.
- Chỉ `extreme_point_best_fit` và `extreme_point_ffd` được hỗ trợ trong checkpoint
  này. Thuật toán khác bị reject sớm với thông báo rõ ràng.
- Strict mode chỉ xét cardinality ban đầu. Adaptive mode tăng dần đến giới hạn tối
  đa sau khi áp dụng lower bound an toàn.
- Hard precheck chạy trước construction. Heuristic failure không được diễn giải là
  chứng minh bất khả thi toán học.
- Objective của candidate invalid bị ẩn. Independent validator Level 1 vẫn là
  cổng quyết định cuối.
- Streamlit hiển thị riêng catalog size, số container ban đầu, số tối đa và cờ tự
  tăng. Tính năng chỉ xuất hiện với hai thuật toán được hỗ trợ.

## Tính tái lập

Run snapshot chứa toàn bộ catalog đã xét. Manifest ghi catalog row count, số
physical container khả dụng, số type tương đương, target ban đầu, target tối đa và
chế độ tự tăng. Instance ID có hậu tố `target<N>` để không nhầm với semantics
legacy.

## Hệ quả và giới hạn

- Người dùng có thể yêu cầu một container và để solver tìm container phù hợp/rẻ
  trong toàn catalog.
- Default Level 1 và toàn bộ Level 2–8 không đổi.
- EMS, Hill Climbing, Simulated Annealing và MILP chưa dùng contract promotion này.
- Catalog lớn vẫn dùng bounded heuristic; kết quả không chứng minh subset tối ưu.
