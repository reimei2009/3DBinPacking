# Benchmark portfolio Best Fit + MES cho Level 4–5

## Mục tiêu

Benchmark đánh giá việc chạy Best Fit và MES trong cùng một request rồi chỉ giữ nghiệm
hợp lệ tốt hơn. Đây là evidence nghiên cứu; portfolio **không được promote**.

## Protocol

Mỗi Level dùng nguồn qualified 1.000 kiện/500 container và 84 bài đã khóa:

- 60 bài stable-random;
- 18 bài stress (`largest_volume`, `heaviest`, `payload_pressure`);
- 6 bài prefix regression;
- ba repeat, tổng 252 lượt mỗi Level và 504 lượt toàn bộ.

Repair tắt. Best Fit chạy trước với budget được bảo vệ, MES chạy sau. Mỗi child candidate
đều qua independent validation và nghiệm cuối được chọn theo số container rồi chi phí.

## Kết quả

| Level | VALID | Deterministic | Bài cải thiện | Runtime median/Best Fit | Kết quả |
|---|---:|---:|---:|---:|---|
| Level 4 | 252/252 | 84/84 | 36/84 | 1,760× | PASS riêng |
| Level 5 | 252/252 | 83/84 | 36/84 theo median | 2,219× | FAIL |

Level 5 có một repeat 500 kiện, random seed 307, trong đó MES dừng `TIME_LIMIT` sau
khoảng 1.049 giây child runtime. Best Fit incumbent vẫn hợp lệ nên final row vẫn có
`success_rate=1.0`. Điều này minh họa rằng success của nghiệm cuối không đồng nghĩa
portfolio đã đạt deterministic và runtime gate.

## Quyết định

Quyết định tổng thể là **NOT_PROMOTED** vì protocol yêu cầu cả hai Level cùng đạt.
Portfolio không xuất hiện trên UI, không trở thành mặc định và implementation không
được đưa vào `develop`. Không tạo V2 trong batch này.

Evaluator và report:

- CLI: `scripts/build_constructor_portfolio_evidence.py`;
- JSON: `docs/reports/manual/level_04_05_constructor_portfolio_20260820.json`;
- báo cáo đọc nhanh: `docs/reports/manual/level_04_05_constructor_portfolio_20260820.md`.

Các output benchmark lịch sử không bị sửa hoặc ghi đè.
