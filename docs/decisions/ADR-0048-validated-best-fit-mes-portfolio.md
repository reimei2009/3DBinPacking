# ADR-0048 — Portfolio Best Fit và MES có kiểm định

## Trạng thái

**NOT_PROMOTED — kết thúc thử nghiệm V1 ngày 2026-08-20.**

## Bối cảnh

MES thường nhanh và tạo nhiều nghiệm dùng ít container hơn Best Fit, nhưng vẫn thua
Best Fit ở một số bài stress. Portfolio V1 thử chạy Best Fit và MES dưới cùng một
deadline, independent-validate từng candidate rồi giữ nghiệm tốt hơn theo objective
chính thức `(số container, tổng chi phí)`.

Protocol yêu cầu cả Level 4 và Level 5 cùng đạt correctness, deterministic, runtime và
memory gate trước khi portfolio được expose hoặc trở thành lựa chọn khuyến nghị.

## Evidence

- Level 4: `252/252 VALID`, `84/84` nhóm deterministic, 36/84 bài cải thiện,
  runtime median `1,760×` Best Fit — đạt gate riêng.
- Level 5: `252/252 VALID`, nhưng chỉ `83/84` nhóm deterministic và runtime median
  `2,219×` Best Fit — không đạt gate.
- Một repeat Level 5 tại stable-random seed 307/500 kiện để MES dừng `TIME_LIMIT`;
  Best Fit incumbent vẫn được giữ nên nghiệm cuối hợp lệ, nhưng objective khác hai
  repeat còn lại.
- Cả 504 lượt đều chọn đúng child hợp lệ tốt nhất; không có objective LOSS.

Evidence bất biến nằm tại
`docs/reports/manual/level_04_05_constructor_portfolio_20260820.{json,md}`.

## Quyết định

- Không promote portfolio lên UI hoặc thuật toán mặc định.
- Giữ capability ở mức `experimental`, chỉ dùng CLI/benchmark trên research branch.
- Không đưa implementation V1 vào `develop` và không tạo Portfolio V2 trong batch này.
- Không chạy recovery vì Level 5 vẫn không đạt runtime median ngay cả khi repeat bất
  thường được chạy lại.

## Hệ quả

Best Fit, FFD và MES riêng tiếp tục là các constructor được nghiệm thu. Bước nghiên cứu
tiếp theo phải phân tích reliability của deadline MES và phân biệt CPU bottleneck với
máy sleep/tải ngoài trước khi thay đổi thuật toán.
