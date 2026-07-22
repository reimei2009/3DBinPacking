# Extreme-Point Best Fit Decreasing

Thuật toán dùng chung engine cho Level 1 và Level 2. Level 1 dùng policy hình học/tải trọng; Level 2 bổ sung exact union-area và center-support cho từng candidate. Validator độc lập của level đang chạy vẫn là nguồn quyết định cuối cùng.

`extreme_point_best_fit` là heuristic tham lam, xác định và chạy bằng CPU cho Level 1. Thứ tự kiện giống FFD: giảm dần theo thể tích, cạnh lớn nhất, khối lượng rồi ID. Thuật toán vẫn tìm subset container theo số lượng nhỏ nhất trước và chi phí tổng nhỏ nhất sau.

Khác với First Fit, mỗi kiện được thử trên toàn bộ cặp `(container, extreme point)` khả thi. Ứng viên được chọn bằng điểm từ điển:

1. ưu tiên container đã mở để không tăng số container sử dụng;
2. nếu phải mở container, ưu tiên chi phí tăng thêm thấp hơn;
3. ưu tiên thể tích dư nhỏ hơn;
4. ưu tiên tải trọng dư nhỏ hơn;
5. ưu tiên mức tăng occupied bounding volume nhỏ hơn;
6. dùng bounding volume sau xếp và thứ tự bottom-left-back làm tie-break xác định.

Tất cả ứng viên phải vượt qua cùng kiểm tra fixed orientation, container boundary, payload và positive-volume non-overlap trong `extreme_point_core.py`. Nghiệm hoàn chỉnh tiếp tục được kiểm tra bởi validator Level 1 độc lập.

Best Fit thường tốn thời gian hơn FFD vì không dừng tại ứng viên khả thi đầu tiên. Nó vẫn là heuristic: `FEASIBLE` không chứng minh tối ưu toàn cục, và `INFEASIBLE_HEURISTIC` không chứng minh bài toán vô nghiệm. Thuật toán không xoay kiện và không mô hình hóa support, stacking hoặc stability.
