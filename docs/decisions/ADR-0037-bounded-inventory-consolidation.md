# ADR-0037: Consolidation có giới hạn sau inventory construction

## Bối cảnh

Nghiệm complete đầu tiên của heuristic là một incumbent hợp lệ, không phải bằng
chứng tối ưu. Nghiệm vẫn có thể dùng dư container do thứ tự kiện, lựa chọn
extreme point hoặc do một vùng trống không thể tiếp cận bằng relocation đơn.

## Quyết định

`BoundedInventoryConsolidator` là implementation canonical dùng chung. Khi được
bật, component thực hiện theo thứ tự:

1. xếp hạng container cần đóng theo số kiện, thể tích hàng, tải trọng, chi phí
   và ID;
2. thử relocation vào các container đang mở còn lại;
3. với Level 2, dựng support closure bắc cầu để không bỏ dependent ở lại;
4. dùng failed-item evidence để xếp hạng tối đa ba destination, tìm blocker
   hình học và mở rộng toàn bộ support closure liên quan;
5. thử adaptive cluster destroy/repack với neighborhood tăng dần
   `4 → 8 → 16 → 24` và portfolio item order bounded;
6. nếu local operators chưa cải thiện, tiếp tục portfolio rebuild theo
   cardinality từ gần incumbent xuống capacity lower bound;
7. chỉ thay incumbent khi candidate complete, qua independent validator của
   level và tốt hơn theo `(số container, chi phí)`.

Extreme-Point core nhận `construction_initial_placements` nội bộ để giữ cố định
phần nghiệm không bị phá. Đây không phải input công khai và không được đọc từ
output của run trước.

Level 1 cung cấp singleton closure. Level 2 cung cấp closure từ exact-support
graph. Consolidator không hard-code level ID; validator được truyền vào bằng
callback từ composition root của từng level.

## Ngân sách

Ba local phase dùng tỷ lệ mặc định `35% / 25% / 40%` cho relocation,
support-closure và adaptive cluster repack. Candidate cap, target-container cap,
destination cap, beam width và neighborhood cap vẫn áp dụng khi người dùng chọn
chế độ không giới hạn thời gian.
Phần ngân sách còn lại được dùng cho rebuild portfolio hiện có.

## Hệ quả

- Incumbent hợp lệ không bị mất khi candidate lỗi, invalid hoặc timeout.
- Không mở container mới trong elimination phase.
- Utilization chỉ là guidance; objective chính vẫn là số container rồi chi phí.
- `heuristic_consolidation_failed` không phải chứng minh bất khả thi.
- Metadata ghi operator, target, rejection, runtime và container trước/sau để
  CLI, UI và báo cáo có thể giải thích kết quả.
