# Screening Projected Extreme Point — 2026-08-10

## Provenance

- Suite: `config/level_01/benchmarks/projected_ep_screening_manual.yaml`
- Aggregate run: `20260810T040159048533Z__level_01__benchmark__seed42`
- Quy mô: 3 profile × 4 thuật toán × 2 repeat.
- Semantics: Level 1, fixed orientation, independent validation bắt buộc.

## Kết quả

Tất cả 24 source run đều thành công và `VALID`; mỗi cặp repeat có một placement
signature duy nhất. Trên cả ba profile, projected Best Fit hòa canonical Best
Fit và projected FFD hòa canonical FFD theo objective chính thức:

- `WIN = 0`;
- `TIE = 6`;
- `LOSS = 0`.

Projected provider tạo thêm overhead nhỏ ở phần lớn case. Bộ screening nhỏ chưa
chứng minh cải thiện số container hoặc chi phí.

## Quyết định

`NOT_PROMOTED`. Hai algorithm projected-EP tiếp tục là comparator CLI/benchmark,
ẩn khỏi Streamlit và không thay solver mặc định. Gate `WIN > LOSS` chưa đạt dù
validity và deterministic đã đạt. Chỉ đánh giá lại khi có corpus candidate-heavy
hoặc external MPV fixed-orientation đã chuẩn hóa.
