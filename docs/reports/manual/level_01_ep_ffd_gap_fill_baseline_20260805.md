# Baseline EP–FFD Look-ahead Gap Filling — Level 1

## Kết luận

Trạng thái đánh giá: **NOT_PROMOTED**.

`extreme_point_ffd_gap_fill` được giữ lại như một comparator nghiên cứu của
Level 1. Thuật toán không thay thế `extreme_point_ffd`, không được hiển thị trên
Streamlit và chưa được port sang các level sau.

## Giả thuyết nghiên cứu

Gap Fill giữ hàng đợi FFD nhưng, sau khi đặt head item, có thể chèn tối đa một
item nằm trong cửa sổ look-ahead vào một Extreme Point bị giới hạn. Phép chèn:

- chỉ dùng container đã mở trong fixed subset;
- không được tự mở container mới;
- dùng ray clearance để xếp hạng, không coi Extreme Point là một cuboid trống;
- luôn đi qua orientation provider, feasibility policy và independent validator.

Official objective của Level 1 vẫn là ít container nhất, sau đó chi phí thấp
nhất. Search score hoặc compactness không thay thế official objective.

## Bằng chứng ngữ nghĩa

Fixture bốn item được thiết kế để tạo một khe cục bộ có kết quả:

| Thuật toán | Container đã dùng | Chi phí | Validation |
|---|---:|---:|---|
| EP–FFD | 2 | 3 | VALID |
| EP–FFD Gap Fill | 1 | 1 | VALID |

Fixture chứng minh state machine và phép chèn hoạt động đúng. Nó không phải
bằng chứng rằng Gap Fill cải thiện tổng quát trên dữ liệu thực.

## Controlled A/B trên dữ liệu thực

Benchmark ban đầu dùng năm profile `20 items / 5 containers`: prefix,
stable-random 101/202, volume-stratified và largest-volume.

- Benchmark ID: `20260805T091533874456Z__level_01__benchmark__seed42`.
- Kết quả: **0 WIN / 5 TIE / 0 LOSS**.
- Mọi nghiệm hoàn chỉnh đều qua independent validator.

## Screening không tuning

Screening dùng mười tập `stable_random`, selection seed từ 101 đến 110. Mỗi
profile so sánh hai thuật toán trên cùng item checksum, container catalog,
fixed subset và solver seed.

- Benchmark ID: `20260805T095904263796Z__level_01__benchmark__seed42`.
- Mười profile có mười `selected_item_ids_checksum` khác nhau.
- Trong từng profile, hai thuật toán có cùng input checksum.
- Placement signature khác nhau, chứng minh Gap Fill thực sự thay đổi construction.
- Kết quả: **0 WIN / 10 TIE / 0 LOSS**.
- Runtime trung bình EP–FFD: khoảng `1.25 ms`.
- Runtime trung bình Gap Fill: khoảng `3.45 ms`.

## Gate generated 1.000 items / 100 container

Hai gate dùng cùng full fleet physical 100 container, không bật inventory search,
để cô lập tác động của Gap Fill. Mỗi cặp A/B có cùng input fingerprint, item
checksum, container checksum và seed.

- Gate A (`i100`): prefix là TIE; stable-random 101 là LOSS (23 → 24 container);
  stable-random 202 và 303 là TIE.
- Gate B (`i300`): prefix, stable-random 101 và 303 là TIE; stable-random 202 là
  LOSS (47 → 48 container).
- Mọi nghiệm hoàn chỉnh đều `VALID`, không timeout. Gate C `i500` không chạy vì
  Gate A/B không tạo WIN.

Tổng hợp A/B ngoài fixture ngữ nghĩa: **0 WIN / 21 TIE / 2 LOSS**. Gap Fill có thể
tạo bố trí cục bộ khác nhưng cũng có thể chặn item lớn xuất hiện sau đó. Vì vậy nó
chưa phải cải tiến tổng quát của FFD và không được promote.

## Diễn giải

Gap Fill tạo placement khác nhưng official objective không đổi. Điều này cho
thấy heuristic có tác động tới bố trí cục bộ, song tác động chưa đủ để đóng một
container hoặc chuyển sang tập container rẻ hơn. Container count và cost là
objective rời rạc, do đó một thay đổi compactness không tự động trở thành WIN.

## Quyết định

- Giữ EP–FFD chuẩn làm baseline.
- Giữ Gap Fill dưới vai trò `research_comparator`, CLI/benchmark only.
- Không chạy Gate C `i500`, không tích hợp inventory-aware orchestration.
- Không port Gap Fill sang Level 2–8.
- Không tuning bằng chính các selection seed 101–110.

## Điều kiện mở lại nghiên cứu

Chỉ mở lại khi có ít nhất một trong các bằng chứng sau:

- dataset mới đa dạng hình học hơn;
- failure analysis cho thấy FFD thất bại do fragmentation cục bộ;
- constrained EP xuất hiện thường xuyên và có item look-ahead phù hợp;
- xuất hiện ít nhất một WIN ngoài fixture được thiết kế riêng;
- một compactness objective mới được phê duyệt và version hóa rõ ràng.

Các benchmark output lịch sử không được commit; benchmark ID trong báo cáo là
tham chiếu tái lập cục bộ.
