# ADR-0036: Kích hoạt có kiểm soát inventory-aware search cho Level 2

## Bối cảnh

Level 1 đã có inventory normalization, hard precheck, lower bound và lazy
ranked subset search dùng chung. Level 2 cần tìm catalog lớn nhưng không được
nhân bản solver hoặc làm yếu ràng buộc exact support.

## Quyết định

Level 2 gọi `InventorySearchOrchestrator` chung chỉ khi
`container_search.enabled=true`. Executor Level 2 luôn tạo
`ExactSupportFeasibilityPolicy`; orchestrator chỉ cung cấp subset policy, không
biết hoặc thay đổi feasibility/validator của Level 2.

Chỉ Extreme Point Best Fit và FFD được hỗ trợ. MILP, EMS, Hill Climbing và SA
fail sớm khi inventory search bật. Default Level 2 giữ chế độ cũ để bảo toàn
regression.

## Hệ quả

- Mỗi candidate trong catalog vẫn phải qua exact support policy.
- Validator Level 2 tính lại union support area độc lập từ placement cuối.
- Processed data và output vẫn cô lập theo Level 2.
- Search inventory lớn là heuristic bounded, không phải chứng minh global
  optimum subset.
- Pattern này chỉ được promote sang Level 3–5 sau acceptance gate riêng từng
  level.
