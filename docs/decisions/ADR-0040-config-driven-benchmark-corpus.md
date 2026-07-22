# ADR-0040: Corpus benchmark điều khiển bằng cấu hình

Trạng thái: accepted.

Số thuật toán đã tăng đến mức ma trận item/container ad-hoc không còn tạo phép so sánh khoa học ổn định. Dự án bổ sung corpus YAML có version, case được đặt tên, nhãn quy mô/độ khó, kết quả kỳ vọng, danh sách thuật toán theo case và aggregate artifact bất biến.

Benchmark matrix thông thường vẫn được hỗ trợ. Hai luồng tái sử dụng experiment runner, independent validator, metric, output isolation, manifest và seed semantics hiện có. Corpus chỉ thêm phân loại reference và quality gap, không thay solver hoặc constraint Level 1.

Chỉ kết quả exact `OPTIMAL` được dùng làm objective `proven_optimal`. Case lớn dùng nhãn yếu hơn là `best_known`. Tương tự, chỉ exact `INFEASIBLE` chứng minh bất khả thi; heuristic failure không phải chứng minh.

Checkpoint này expose corpus qua CLI và artifact bất biến. Streamlit chưa đọc corpus trực tiếp; việc promote lên UI cần acceptance riêng để không trộn schema corpus với benchmark matrix hiện tại.
