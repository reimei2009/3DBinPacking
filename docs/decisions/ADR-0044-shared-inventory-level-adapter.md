# ADR-0044 — Adapter inventory dùng chung theo contract từng level

## Trạng thái

Được chấp nhận cho promotion Level 3.

## Bối cảnh

Level 1–2 đã dùng cùng inventory orchestrator nhưng tự lặp lại phần wiring.
Level 3 thêm horizontal orientation. Nếu tái sử dụng orchestration mà không
truyền orientation provider, hard precheck và subset ranking có thể loại nhầm
kiện chỉ vừa container sau khi hoán đổi chiều dài/rộng.

## Quyết định

Sử dụng một `InventoryLevelAdapter` cho Level 1–3. Mỗi level cung cấp executor đã
gắn feasibility policy, orientation provider, independent candidate validator và
support-closure provider. Orientation provider là trường bắt buộc của
`InventorySearchRequest` và được dùng xuyên suốt precheck, subset search,
construction, consolidation và partial-repack guidance.

Level 3 chỉ bật inventory cho Best Fit, FFD và MES. Các thuật toán khác fail rõ
khi inventory được yêu cầu; không fallback ngầm.

## Hệ quả

- Level 3 kế thừa search budget, validated incumbent và repair của Level 2 mà
  không sao chép solver.
- Level 1–2 giữ fixed orientation và behavior cũ.
- Level 4–5 có thể compose policy/validator riêng trên cùng adapter.
- Thay đổi orientation phải qua regression Level 1–2 và gate Level 3 riêng.
