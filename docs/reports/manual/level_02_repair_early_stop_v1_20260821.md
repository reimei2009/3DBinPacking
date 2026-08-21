# Level 2 — Repair Early-stop V1

## Kết luận

Quyết định chính thức: **NOT_PROMOTED**.

Early-stop tiết kiệm thời gian đáng kể nhưng làm xấu official objective ở hai cặp 500 kiện. Vì vậy cơ chế tiếp tục mặc định tắt.

## Evidence

- Coverage: 8 case / 48 lượt; 48 lượt independently `VALID`.
- Deterministic: 16/16 nhóm.
- Paired outcomes: 0 cải thiện / 6 không đổi / 2 regression.
- Median runtime reduction: 69,89%.
- Source commit: `2ce047c8f96bf9f389583b085280ae8d76f63b98`; `git_dirty=false`.

## Các cặp regression

| Thuật toán | Case | Repair chuẩn | Early-stop |
|---|---|---:|---:|
| `extreme_point_best_fit` | `repair_early_stop_random101_i500` | 20 container / 40000 | 21 container / 41700 |
| `extreme_point_ffd` | `repair_early_stop_random101_i500` | 20 container / 40000 | 21 container / 41700 |

Không điều chỉnh threshold chỉ để khớp các case này. Bước tiếp theo là thu thập timeline improvement bằng diagnostic riêng trước khi cân nhắc V2.

## Checksums

- `manifest.json`: `a43650baf7d2201ef0a3f3c21d5be8944877927ad7c1e1a06c63c16ae7a1a091`
- `benchmark/results.csv`: `8cf8c82e5d7c4d5afd398a23c79aaadd2b32f02f67fd7d7de5c63e92a12cf137`
- `benchmark/determinism_evidence.csv`: `98d83a055f67d840af64a198de1058dcb39e757ff6f9f8cf1268266da2da7267`
- `benchmark/repair_early_stop_comparison.csv`: `34aeca0d305370e0845d26e7ed9b4ec09d6bda55a7aaa2cf6517e54009fc2521`
