# ADR-0034: EP–FFD Look-ahead Gap Filling

Trạng thái: **Đã đánh giá — research comparator, không promote**.

`extreme_point_ffd_gap_fill` là comparator Level 1, không thay thế FFD chuẩn.
Nó chỉ dùng Extreme Point như vị trí neo và ray clearance như tín hiệu xếp hạng;
mọi placement vẫn phải qua feasibility policy và validator độc lập. Comparator
chỉ đặt tối đa một item look-ahead sau mỗi head item, không mở container mới và
không phải exact free-space/Maximal Empty Space solver.

Fixture A/B Level 1 dùng C1/C2 kích thước `10×10×1` và bốn item
`HEAD=5×5×1`, `NEXT=6×4×1`, `TALL_GAP=2×6×1`, `GAP_ITEM=2×2×1`.
FFD chuẩn dùng hai container; comparator chèn `GAP_ITEM` sau `HEAD` và dùng
một container. Đây là evidence ngữ nghĩa, không phải benchmark hiệu năng.

Đánh giá trên 15 profile dữ liệu thực `20 items / 5 containers` và 6 profile
generated `1.000 items / 100 container` cho kết quả `0 WIN / 21 TIE / 2 LOSS`.
Các tập stable-random có checksum khác nhau và Gap Fill tạo placement signature
khác FFD, nhưng không giảm container count hoặc cost; hai profile generated còn
dùng thêm một container. Vì vậy FFD chuẩn vẫn là baseline; comparator tiếp tục ẩn
khỏi Streamlit, không được tích hợp inventory-aware search và chưa được port sang
Level 2–8.

Chi tiết bằng chứng và điều kiện mở lại nghiên cứu nằm tại
`docs/reports/manual/level_01_ep_ffd_gap_fill_baseline_20260805.md`.
