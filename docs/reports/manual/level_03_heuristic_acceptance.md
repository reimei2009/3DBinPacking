# Quy trình nghiệm thu heuristic Level 3

Tài liệu này phân biệt hai gate độc lập:

1. heuristic orientation trên fixed subset;
2. shared inventory orchestration trên physical catalog.

Mọi thuật toán trong cùng case phải dùng chung item IDs, catalog, horizontal
orientation profile, exact-support policy, seed và deadline. Chỉ nghiệm complete
và independently `VALID` mới có official objective.

## Gate heuristic fixed subset

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_03\benchmarks\core_heuristics_local.yaml
```

Kiểm tra `benchmark/results.csv`, `summary.csv`, `ranking.csv` và
`pareto_frontier.csv` trong run directory Level 3 mới. Không gộp row khác
`input_fingerprint`.

## Gate inventory promotion

Corpus vật lý dùng đúng nguồn 1.000 kiện/500 container đã qualification. Dữ liệu
được xử lý lại trong namespace Level 3 để kích hoạt horizontal orientation.

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_03\benchmarks\inventory_promotion_20_500_manual.yaml
```

Chạy và đánh giá tuần tự các scale 20, 100, 300 và 500. Best Fit phải tạo nghiệm
`VALID` ở scale hiện tại trước khi dùng scale lớn hơn làm evidence promotion.

## Tiêu chí

| Kiểm tra | Yêu cầu |
| --- | --- |
| Contract | `level=level_03`, orientation `horizontal_rotatable`, exact support bật |
| Validity | Mọi success có `validation_valid=true` |
| Fairness | Cùng case có một fingerprint và selected-item checksum |
| Deterministic | Hai repeat có cùng placement signature và objective |
| Failure | Invalid/timeout không có official objective |
| Isolation | Processed data và output chỉ nằm trong namespace Level 3 |

`INFEASIBLE_HEURISTIC` chỉ là thất bại tìm kiếm trong budget, không phải chứng
minh bài toán vô nghiệm. Inventory UI Level 3 chỉ được xem xét sau khi gate
runtime 20–500 hoàn tất.
