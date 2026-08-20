# Benchmark portfolio Best Fit + MES cho Level 4–5

## Mục tiêu

Benchmark kiểm tra việc chạy hai constructor trong cùng một request rồi giữ nghiệm
hợp lệ tốt hơn. Đây là candidate nghiên cứu, chưa phải thuật toán mặc định và chưa
được mở trên UI.

## Protocol

Mỗi Level dùng nguồn qualified 1.000 kiện / 500 container và 84 bài đã khóa:

- 60 bài stable-random;
- 18 bài stress (`largest_volume`, `heaviest`, `payload_pressure`);
- 6 bài prefix regression;
- ba repeat, tổng 252 lượt mỗi Level và 504 lượt cho Level 4–5.

Repair tắt. Best Fit chạy trước, MES chạy sau. Mỗi child candidate được kiểm định
độc lập; kết quả cuối chọn theo số container rồi đến chi phí.

## Artifact

Mỗi run sinh `benchmark/constructor_portfolio_comparison.csv`, ghi objective,
validation, runtime của từng constructor, constructor được chọn, kết quả WIN/TIE/LOSS
so với Best Fit và tỷ lệ runtime.

## Gate

- tất cả kết quả thành công phải `VALID`;
- kết quả cuối bằng child objective tốt nhất;
- không có LOSS so với child hợp lệ;
- deterministic qua ba repeat;
- runtime trung vị không quá 1,8 lần Best Fit và p95 không vượt deadline;
- memory overhead không quá 20% so với evidence Best Fit cùng corpus;
- mỗi Level có ít nhất một WIN so với Best Fit.

Chỉ khi cả hai Level đạt mới expose portfolio và inventory Level 4–5 trên UI.
Nếu một Level không đạt, evidence được ghi `NOT_PROMOTED` và không tạo V2 trong batch.
