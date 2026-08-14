# Acceptance phân phối và profiling Level 3–5

Ba level dùng chung nguồn 1.000 kiện và kho 500 container, nhưng mỗi level có ràng buộc khác nhau. Vì vậy kết quả chỉ được so sánh chất lượng giữa các thuật toán trong cùng một level, trên đúng cùng bài kiểm tra.

Mỗi level có ba corpus ứng viên: random 60 bài, stress 18 bài và prefix 6 bài. Mỗi bài chạy Best Fit, FFD và MES ba lần; tổng là 756 lượt. Random là nguồn duy nhất cho kết luận WIN/TIE/LOSS; stress và prefix được báo riêng.

Chạy lần lượt random, stress rồi prefix cho từng level. Khi một run bị gián đoạn, dùng `--recover-from <run-dir> --rerun-failed-only` để tái sử dụng các lượt đã independently `VALID`.

Sau khi cả ba tầng đạt gate, chạy `scripts/profile_cross_level_benchmark.py`. Profiling chỉ là chẩn đoán: nó không tham gia ranking, objective hoặc evidence canonical. Báo cáo profiling phân tách thời gian chuẩn bị dữ liệu, precheck/subset, construction, validation, reporting và các hàm nóng của candidate/support/overlap/load-transfer.

Không promote Level 6 cho đến khi evidence và profiling hoàn chỉnh, sau đó mới chọn một cải tiến có dữ liệu chứng minh.
