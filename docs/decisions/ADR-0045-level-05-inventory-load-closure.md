# ADR-0045 — Inventory Level 5 và closure bảo toàn tải truyền

## Trạng thái

Được chấp nhận cho gate promotion Level 5.

## Bối cảnh

Level 5 bổ sung tải truyền tĩnh đệ quy lên Level 4. Partial repack không được di
chuyển một supporter nhưng bỏ lại kiện phụ thuộc phía trên, vì candidate trung
gian khi đó không còn biểu diễn đúng support và load-transfer graph.

## Quyết định

Level 5 compose `InventoryLevelAdapter` hiện có thay vì tạo inventory solver mới.
Best Fit, FFD và MES dùng chung orchestration; mỗi candidate có khả năng thay
incumbent phải qua independent Level 4 validation và Level 5 load validation.

Canonical repair dùng transitive exact-support closure. Mọi load-transfer edge
đều là một positive-area support contact nên closure này bao phủ toàn bộ quan hệ
truyền tải. Closure bảo thủ được chấp nhận để ưu tiên correctness.

## Hệ quả

- Không sao chép precheck, subset search, budget hoặc consolidation.
- Timeout hay candidate invalid không làm mất validated incumbent.
- Closure có thể làm neighborhood lớn hơn tối thiểu và giảm số repair candidate;
  đây là trade-off có chủ ý, chỉ tối ưu sau profiling.
- Gate dùng capacity synthetic nên không được diễn giải thành chứng nhận cơ học.
