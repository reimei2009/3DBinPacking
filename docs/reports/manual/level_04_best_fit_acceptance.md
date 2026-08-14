# Quy trình nghiệm thu Level 4

Tài liệu này phân biệt hai nhóm evidence: baseline lịch sử trên fixture nhỏ và
promotion shared inventory trên physical corpus 1.000 item/500 container.

## Gate inventory hiện hành

Chạy full tests, sau đó chạy benchmark promotion:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check

.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_04\benchmarks\inventory_promotion_20_500_manual.yaml
```

Suite tạo 24 lượt: bốn quy mô × ba constructive solver × hai repeat. Repair tắt
để đo riêng construction có orientation, exact support và stackability.

## Điều kiện đạt

| Nhóm | Yêu cầu |
| --- | --- |
| Coverage | Đúng 20, 100, 300 và 500 item; Best Fit, FFD và MES. |
| Validity | Mọi success independently `VALID`; invalid/timeout không có objective. |
| Stackability | Mỗi item ngoài sàn có cha hợp lệ, cùng group và không vượt chain cap. |
| Fairness | Thuật toán trong cùng case dùng chung fingerprint, items, catalog và deadline. |
| Determinism | Hai repeat có cùng objective và placement signature. |
| Isolation | Mọi source run nằm dưới `outputs/level_04/runs/`. |

Official objective vẫn ưu tiên ít container rồi chi phí thấp. Runtime được báo
riêng và không được dùng để đánh đổi thêm container. Level 3 không phải baseline
chất lượng trực tiếp vì Level 4 có thêm hard constraint stackability.

## Evidence lịch sử

Các suite `best_fit_baseline_local.yaml`, `core_constructive_local.yaml`,
`local_search_local.yaml`, `metaheuristic_local.yaml` và `portfolio_local.yaml`
vẫn là evidence nghiên cứu trên contract Level 4. Chúng không được gộp trực tiếp
với inventory promotion nếu input fingerprint khác nhau.

Không coi heuristic failure là chứng minh bất khả thi. Không commit run directory
hoặc sao chép CSV sinh tự động vào tài liệu nguồn.
