# ADR-0046: Chỉ mục contact/support dùng chung trong construction

## Trạng thái

V1 **không đạt promotion gate**. V2 đang thử nghiệm có giới hạn; mặc định tắt.

## Bối cảnh

Profiling Level 4–5 cho thấy construction chiếm khoảng 71% thời gian toàn pipeline.
Trong construction, exact support và việc tìm các mặt tiếp xúc là nhóm chi phí lớn.
Đường cũ quét toàn bộ placement trong container cho mỗi candidate.

## Quyết định

Thêm `ContactSupportIndex` dùng chung cho Extreme Point Best Fit, FFD và Maximal
Empty Spaces Best Fit. Mỗi container lập chỉ mục mặt trên theo cao độ và dùng lọc
giao nhau XY trước khi gọi `contact_rectangle` hiện hành.

Chỉ mục chỉ là broad phase, không phải nguồn quyết định hình học:

- `contact_rectangle`, union area, stackability và load transfer giữ nguyên semantics;
- chỉ cập nhật khi một placement được commit;
- seeded state và partial repack dựng lại chỉ mục theo thứ tự deterministic;
- candidate bị từ chối không thay đổi chỉ mục;
- independent validator tiếp tục quét brute-force từ raw input.

Cấu hình nằm riêng trong từng constructor:

```yaml
contact_support_index:
  enabled: false
```

Level 2–3 và behavior mặc định hiện tại không thay đổi. Level 4–5 chỉ được bật mặc
định sau khi A/B chứng minh cùng status, objective, placement signature và rejection
counters, đồng thời đạt gate runtime và memory đã công bố.

## Hệ quả

Telemetry V2 ghi version, query thực tế, cache hit/miss, exact-contact checks,
thời gian trong index, số placement được broad phase giữ lại và số lần quét ước
tính tránh được. Benchmark A/B là research evidence, không tham gia ranking
canonical.

V1 đạt correctness nhưng chỉ cải thiện construction trung vị 6,92% ở Level 4
và làm Level 5 chậm hơn 1,11%, nên không được bật mặc định. Dự án chỉ cho phép
một vòng V2 nhằm giảm overhead query lặp. Nếu V2 không đạt toàn bộ gate ở cả
Level 4 và Level 5, hướng index này kết thúc ở trạng thái `NOT_PROMOTED`; không
mở V3.
