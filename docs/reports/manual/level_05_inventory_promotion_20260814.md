# Evidence promotion inventory Level 5 — 2026-08-14

## Kết luận

Gate prefix Level 5 đạt yêu cầu kỹ thuật để dùng shared inventory orchestration
cho Best Fit, FFD và MES Best Fit.

- 4 bài: 20, 100, 300 và 500 kiện;
- 3 constructor, 2 repeat: 24 lượt;
- 24/24 lượt complete và independently `VALID`;
- 12/12 nhóm case–algorithm có cùng objective và placement signature;
- mọi thuật toán trong cùng case dùng chung input fingerprint và item checksum;
- không có failure mang official objective;
- toàn bộ source run nằm dưới `outputs/level_05/runs/`.

Artifact nguồn:

```text
outputs/level_05/runs/20260814T071247022306Z__level_05__benchmark__seed42
```

## Kết quả objective

| Số kiện | Best Fit | FFD | MES Best Fit |
| ---: | ---: | ---: | ---: |
| 20 | 2 container / 4.000 | 2 / 4.000 | 2 / 4.000 |
| 100 | 5 / 10.000 | 5 / 10.000 | 5 / 10.000 |
| 300 | 13 / 26.000 | 13 / 26.000 | 13 / 26.000 |
| 500 | 22 / 44.000 | 22 / 44.000 | 20 / 40.000 |

MES tạo objective tốt hơn ở case prefix 500 và chạy nhanh hơn trong gate này.
Không được suy rộng thành kết luận MES tốt nhất nói chung vì gate chỉ có bốn
prefix case, không phải phân phối nhiều selection seed.

## Phạm vi bằng chứng

Feasibility policy là horizontal orientation + exact support + stackability +
static recursive load bearing. Capacity dùng profile synthetic
`synthetic_weight_factor_v1`; evidence chứng minh correctness phần mềm theo
contract Level 5, không chứng minh an toàn cơ học hoặc độ bền vật liệu thực tế.
