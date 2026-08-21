# Nghiệm thu repair UI Level 3

- Trạng thái: **PASS**.
- Lượt chạy: 72/72.
- So sánh ghép cặp: 18/18.
- Nhóm deterministic: 36/36.
- Kết quả A/B: `{'IMPROVED': 6, 'UNCHANGED': 12}`.

- Runtime tăng trung vị: 44.127 giây.
- Hệ số runtime trung vị: 10.502x.

## Kết quả theo thuật toán

`{'extreme_point_best_fit': {'comparison_count': 6, 'improved': 3, 'unchanged': 3, 'regression': 0}, 'extreme_point_ffd': {'comparison_count': 6, 'improved': 3, 'unchanged': 3, 'regression': 0}, 'maximal_space_best_fit': {'comparison_count': 6, 'improved': 0, 'unchanged': 6, 'regression': 0}}`

## Kết quả theo quy mô

`{'100': {'comparison_count': 6, 'improved': 0, 'unchanged': 6, 'regression': 0}, '300': {'comparison_count': 6, 'improved': 4, 'unchanged': 2, 'regression': 0}, '500': {'comparison_count': 6, 'improved': 2, 'unchanged': 4, 'regression': 0}}`

## Provenance

- Run nguồn: `20260817T083235312710Z__level_03__benchmark_corpus__level_03_repair_ab_100_500_v1__seed42`.
- Commit nguồn: `3d38f115e93fc7db73fdb4f900ec8b821ed47b8e`.
- Git dirty: `True`.
- Manifest SHA-256: `802451d784ceb00854a712b95a35a0409f618b2ef4bb38d914d44bda82d5a22f`.
- Results SHA-256: `982e6f05949cf5ffe382e88409126cddec76a908a5a32ecd59f315f6e2ad7732`.
- Repair comparison SHA-256: `808bd18646da91b200760cea466e606beca41e0d6ec40b1964924a2adeefbe1f`.
- Ngoại lệ provenance được chấp nhận: Run dùng đúng commit 3d38f11; trạng thái dirty chỉ gồm hai tài liệu WIP đã sửa và hai file local không thuộc solver, config hoặc dữ liệu benchmark.

## Lỗi gate

- Không có.
