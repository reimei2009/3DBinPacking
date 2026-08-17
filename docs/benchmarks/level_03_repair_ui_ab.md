# A/B repair UI Level 3

## Mục tiêu

Repair là bước cải thiện sau khi construction đã tạo được một nghiệm hợp lệ.
Nó có thể thử giảm số container hoặc chi phí, nhưng không thay thế independent
validator và không được phép làm mất incumbent hợp lệ.

Level 3 hiện giữ `repair_ui_qualified=false`. Vì vậy cả chạy đơn và benchmark
tùy chỉnh trên Streamlit đều ẩn repair và luôn gửi
`consolidation.enabled=false`. Core repair vẫn dùng được qua config/CLI để tạo
evidence trước khi quyết định mở UI.

## Protocol

Nguồn duy nhất là corpus đã qualification gồm 1.000 kiện và 500 physical
container thuộc 10 loại. Sáu input ghép cặp gồm:

- 100, 300 và 500 kiện;
- prefix và stable-random seed 101 tại mỗi quy mô.

Mỗi input chạy Extreme Point Best Fit, Extreme Point FFD và Maximal Empty
Spaces Best Fit. Mỗi constructor chạy hai repeat với repair tắt và hai repeat
với repair bật, tổng cộng 72 lượt.

| Số kiện | Start | Max | Deadline | Budget repair |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 3 | 7 | 60 giây | 20 giây |
| 300 | 9 | 18 | 120 giây | 45 giây |
| 500 | 14 | 28 | 180 giây | 60 giây |

Repair không được dùng validation reserve 3 giây. Hai variant trong cùng input
giữ nguyên item IDs, catalog, orientation `XYZ/YXZ`, exact-support rules,
start/max, seed và global deadline.

## Gate mở UI

Capability chỉ được đổi thành `true` khi:

- đủ 72/72 lượt complete và independently `VALID`;
- 36 nhóm input–constructor–variant deterministic về objective và placement;
- 18 so sánh input–constructor không có objective loss;
- có ít nhất một objective win;
- timeout hoặc candidate exhaustion vẫn giữ validated incumbent;
- runtime repair và termination reason đầy đủ;
- mọi row invalid/incomplete có objective rỗng.

Nếu không đạt, evidence mang trạng thái `NOT_PROMOTED` và UI tiếp tục ẩn
repair. Không thay exact-support threshold để vượt gate.

## Chạy thủ công

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_03\benchmarks\repair_ab_100_500_manual.yaml
```

Sau khi lệnh in thư mục corpus, đánh giá gate bằng:

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_level3_repair_ab.py `
  --run-dir <thu-muc-corpus-vua-in>
```

Script chỉ đọc artifact đã tạo và ghi report vào chính run directory. Nó không
tự sửa capability UI và không rewrite output lịch sử.
