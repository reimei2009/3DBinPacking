# A/B Contact/Support Index cho Level 4–5

## Mục đích

Benchmark này đo riêng tác động của broad-phase index trong construction. Hai
variant dùng cùng items, kho container, ràng buộc, start/max, deadline và seed.
Repair tắt. Official objective vẫn là số container rồi chi phí.

Mỗi Level có 6 input ghép cặp:

- stable-random seed 101 tại 100, 300 và 500 kiện;
- `largest_volume`, `heaviest` và `payload_pressure` tại 500 kiện.

Hai variant × ba constructor × ba repeat tạo 108 lượt cho mỗi Level. Runner xen
kẽ thứ tự variant theo cặp để giảm bias do cache và nhiệt độ máy.

## Chạy thủ công

Chạy tuần tự, không chạy song song:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_04\benchmarks\contact_support_index_ab_manual.yaml

.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_05\benchmarks\contact_support_index_ab_manual.yaml
```

Kết quả so sánh nằm tại:

```text
outputs/<level>/runs/<run_id>/benchmark/contact_index_comparison.csv
```

## Cách đọc gate

`correctness_gate_passed` phải đúng cho mọi hàng. Status, objective, placement
signature và rejection counters giữa hai variant phải giống nhau. Sau đó mới đọc
construction speedup, wall-runtime speedup và memory overhead.

Chỉ promote mặc định khi từng Level đạt đồng thời:

- median construction toàn Level giảm ít nhất 20%;
- wall runtime median không tăng;
- không constructor nào tăng construction quá 5%;
- peak memory tăng không quá 20%;
- mọi nghiệm thành công independently `VALID` và deterministic.

Artifact A/B là research evidence, không được gộp vào ranking canonical.
