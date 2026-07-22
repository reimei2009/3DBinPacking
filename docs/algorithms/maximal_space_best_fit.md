# Maximal Empty Spaces — Best Fit Decreasing

Engine Maximal Empty Spaces được dùng chung cho Level 1 và Level 2. Ở Level 2, origin của mỗi empty space chỉ được chấp nhận nếu candidate vượt qua exact union-area và center-support policy; vì vậy một khoảng trống hình học ở cao độ lớn chưa tự động được xem là có mặt đỡ.

`maximal_space_best_fit` là constructive heuristic xác định, chạy CPU cho Level 1. Item được sắp giảm dần theo thể tích, cạnh lớn nhất, khối lượng và ID. Thuật toán duyệt subset container theo số lượng ít nhất trước, rồi tổng chi phí thấp nhất.

Mỗi container bắt đầu với một khối trống bằng toàn bộ thể tích bên trong. Sau khi đặt item, mọi khối trống giao với item được tách thành tối đa sáu slab: trái, phải, trước, sau, dưới và trên. Các khối suy biến, trùng lặp hoặc bị khối khác chứa hoàn toàn được loại bỏ. Các khối trống còn lại có thể giao nhau; kiểm tra non-overlap trực tiếp với mọi placement đã có là lớp an toàn bắt buộc.

Với mỗi item, thuật toán đánh giá mọi cặp `(container, empty space)` khả thi và chọn theo thứ tự từ điển:

1. container đã mở;
2. chi phí tăng thêm nếu phải mở container;
3. thể tích dư của empty space;
4. thể tích dư toàn container;
5. payload dư;
6. mức tăng occupied bounding volume;
7. tọa độ bottom-left-back và tie-break ổn định.

Độ phức tạp thực tế phụ thuộc số khối trống được sinh ra. Metadata và `solver_summary.json` ghi số space đã đánh giá, sinh, prune và số space hoạt động cực đại để theo dõi hiện tượng tăng trưởng này.

Thuật toán chỉ trả `FEASIBLE` sau khi validator Level 1 độc lập chấp nhận nghiệm. `INFEASIBLE_HEURISTIC` chỉ có nghĩa heuristic không tìm được cách xếp; không chứng minh bài toán vô nghiệm. EMS không xoay item và không mô hình hóa support, stacking hoặc stability.
