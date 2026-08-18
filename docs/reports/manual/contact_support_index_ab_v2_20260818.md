# Contact/Support Index V2 — Evidence ngày 2026-08-18

Trạng thái: **NOT_PROMOTED**.

Index tiếp tục mặc định tắt. Best Fit, FFD và MES vẫn dùng đường brute-force hiện hành.

| Level | VALID | Deterministic | Construction trung vị | Wall speedup | Regression >5% | Memory tối đa |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| level_04 | 108/108 | 36/36 | -0.65% | 1.004× | 4 | 2.94% |
| level_05 | 107/108 | 35/36 | 2.24% | 1.028× | 3 | 4.37% |

## Lý do không promote

- `level_04`: median construction improvement is below 20%.
- `level_04`: at least one constructor/case regressed construction by more than 5%.
- `level_05`: corpus run must have status SUCCESS.
- `level_05`: all 108 executions must be successful and independently VALID.
- `level_05`: non-deterministic or incomplete execution group: ('contact_payload_pressure_i500', 'extreme_point_ffd', 'contact_index_enabled').
- `level_05`: selected items mismatch: contact_payload_pressure_i500.
- `level_05`: enabled/disabled correctness equivalence failed.
- `level_05`: median construction improvement is below 20%.
- `level_05`: at least one constructor/case regressed construction by more than 5%.

## Lỗi kỹ thuật quan sát được

- `level_05` / `contact_payload_pressure_i500_enabled` / `extreme_point_ffd` / repeat 2: `KeyError: 'n_items'`.
- Các row lỗi không có official objective và không được dùng cho kết luận chất lượng.

## Quyết định

Không bật index mặc định, không merge implementation V2 vào `develop` và không phát triển V3.
Artifact này là research evidence, không tham gia ranking canonical.

## Provenance

- Commit nguồn: `11e035d82afeb92d60adbaa0d1c7b5c2d2e6ce36`; cả hai manifest ghi `git_dirty=false`.
- `level_04` run: `20260818T034303316073Z__level_04__benchmark_corpus__level_04_contact_support_index_ab_v2__seed42`.
  - manifest SHA-256: `5dd4c04485a2efdc70d2ad69005905e517212de78d6291222db8f3cd8cb0fafb`
  - results SHA-256: `aec82723c4b4aa7be967afbe456b81aca106a907e4a5415e6548fde340b5f947`
  - contact comparison SHA-256: `c8ece463b364c8de6688f2f17561b44edfbca86267dbb35b94f55b9736db6e2e`
- `level_05` run: `20260818T041906338503Z__level_05__benchmark_corpus__level_05_contact_support_index_ab_v2__seed42`.
  - manifest SHA-256: `b9a92ec3fead20b89cf48043986ff9c35f4c3a1032ee66fe5334cc920fc48a8d`
  - results SHA-256: `7c780e5f9363adbc55dd6a0d3af5c95ea0fbec3c077764946b8573dd3001b1ba`
  - contact comparison SHA-256: `a53f853d5a195b513f732efa63452c0011b0b17929a987ba33c8835d14f873e8`
