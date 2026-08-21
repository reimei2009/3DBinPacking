# Evidence độ tin cậy deadline MES

**Mã báo cáo:** `mes_deadline_reliability_20260820`

**Quyết định:** `NO_COOPERATIVE_HARDENING_REQUIRED`

## Kết luận

Không cần mở batch cooperative deadline hardening và không cần subprocess watchdog. Trong
18 lượt chẩn đoán MES ở Level 4–5, toàn bộ nghiệm đều `FEASIBLE`, independently `VALID`,
deterministic và không có dấu hiệu sleep, tranh chấp tài nguyên máy hoặc gián đoạn đồng hồ.

Kết luận này chỉ đóng vấn đề **độ tin cậy deadline MES**. Constructor Portfolio V1 vẫn
`NOT_PROMOTED` vì gate runtime và deterministic Level 5 trước đó không đạt. MES tiếp tục là
research comparator; Level 6 tiếp tục đóng băng.

## Evidence đã khóa

- Lượt hợp lệ: **18/18**.
- Nhóm case–algorithm deterministic: **6**.
- Lượt nhiễu môi trường: **0**.
- Deadline overshoot lớn nhất: **0.000000 giây**.
- Operation dài nhất: **`exact_support`**, **0.01092720 giây**.
- Operation cần harden: **không có**.

| Level | Corpus | Run | SHA-256 manifest | SHA-256 results |
|---|---|---|---|---|
| level_04 | `level_04_mes_deadline_reliability_v1` | `20260820T082930434390Z__level_04__benchmark_corpus__level_04_mes_deadline_reliability_v1__seed42` | `bdf3f25af56d4dee42bdf50f040dcfee0b41916930178537ab356a2fc1bc4952` | `2f23a21146a077bdb066ee9208be44a88680b9bb6957e20124c7c7905b683676` |
| level_05 | `level_05_mes_deadline_reliability_v1` | `20260820T083332717084Z__level_05__benchmark_corpus__level_05_mes_deadline_reliability_v1__seed42` | `1e63495087ef66a895ff53c9ab37db508f184606dda5e1484184b70d55d00931` | `3a28cb69621000b36d083c12f5771af5817648d970049c41404f35f6659bc754` |

Hai run đều được tạo từ commit sạch
`ad0d23c7d5cc59ddb70bde38a5e75fc12e433e49`. Checksum trong bảng là khóa provenance: report phải fail
nếu manifest hoặc kết quả bị thiếu, thay đổi hay không còn khớp nguồn.

## Cách diễn giải

Deadline vẫn được quyết định theo wall-clock và không được tự gia hạn. Observer chỉ đo thêm
wall time, process CPU time và active time của Windows. Ngưỡng mở hardening là operation
active-time trên 1 giây hoặc overshoot sạch trên `max(1 giây, 1% deadline)`; evidence này
không chạm ngưỡng nào.

Không dùng report này để đảo ngược benchmark portfolio, xếp hạng chất lượng solver hoặc
tuyên bố MES tối ưu. Các run diagnostic không tham gia canonical ranking.
