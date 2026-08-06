# ADR-0035: Shared inventory search orchestration

## Bối cảnh

Level 1 đã nghiệm thu bounded inventory search với catalog 500 và 5.000
physical container. Nếu normalization, precheck, lower bound, lazy subset,
deadline và failure metadata được copy vào Level 2–5, các level sẽ nhanh chóng
phân kỳ dù cùng vận hành trên một kho container.

## Quyết định

`algorithms/search/inventory_orchestration.py` là implementation canonical cho
phần điều phối chung. Module nhận constructive executor của level qua protocol;
executor vẫn sở hữu feasibility policy đang active. Validator độc lập vẫn do
pipeline level thực hiện, không được đưa vào orchestration.

Level 1 chỉ delegate khi `container_search.enabled=true`. Khi tắt, executor
legacy được gọi trực tiếp và giữ nguyên behavior trước refactor.

Orchestrator chuẩn hóa các failure sau:

- `PRECHECK_FAILED`: chỉ cho input/capacity proven failure, không gọi executor;
- `INFEASIBLE_HEURISTIC`: search không tìm được packing trong budget;
- `TIME_LIMIT`: hết budget, objective giữ `null`.

## Hệ quả

- Không sao chép inventory solver theo từng level.
- Support, orientation, stackability và load-bearing không nằm trong shared
  orchestrator; chúng tiếp tục thuộc executor/policy của từng level.
- Metadata inventory, fingerprint và selected type distribution có một nguồn
  sự thật duy nhất.
- Metadata động của subset policy được giữ lại, nhưng không được ghi đè evidence
  inventory/precheck đã được tính trước executor.
- Chỉ sau regression Level 1 mới compose Level 2; không promote nhiều level
  trong cùng checkpoint refactor.
