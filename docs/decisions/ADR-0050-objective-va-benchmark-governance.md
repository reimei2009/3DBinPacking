# ADR-0050 — Governance objective và benchmark canonical

Trạng thái: **accepted**.

## Bối cảnh

Project có nhiều heuristic, benchmark nội bộ, MPV academic và artifact lịch sử.
Nếu không tách objective, reference và provenance, một nghiệm tốt quan sát được có
thể bị hiểu nhầm là tối ưu hoặc một run từ working tree chưa sạch có thể được promote
thành canonical.

## Quyết định

Official objective luôn là tuple lexicographic:

```text
(used_container_count, total_container_cost)
```

Policy phụ `utilization_void_support_margin_v1` mặc định tắt. Nó chỉ được tính cho
nghiệm complete, independently `VALID`, và chỉ phân xử khi official objective bằng
nhau. Runtime, compactness hoặc utilization không được đánh đổi thêm container hay
chi phí.

Reference được phân loại độc lập:

- `proven_optimal`: chỉ exact solver kèm bằng chứng tối ưu;
- `best_observed`: nghiệm hợp lệ tốt nhất trên cùng input fingerprint;
- `aggregate_lower_bound`: cận sơ bộ từ volume/payload, không phải nghiệm và không
  chứng minh khả thi hình học hay tối ưu.

Evidence canonical phải khóa SHA-256 của manifest, results, determinism và pairwise
artifact. Functional gate và provenance gate là hai gate riêng. Một corpus có thể
đạt validity/determinism nhưng vẫn không được promote nếu `git_dirty=true`, thiếu
source commit hoặc checksum không khớp.

## Áp dụng hiện tại

Level 2 V1 tiếp tục là canonical. V2 ngày 2026-08-13 đạt functional gate với 84 bài,
756 lượt và 252 nhóm deterministic, nhưng cả ba source run đều `git_dirty=true`.
Trạng thái governance là `CANONICAL_PENDING_CLEAN_RERUN`; registry V2 vẫn là
`research` cho đến khi chạy lại sạch.

MES Level 4–5 được chấp nhận làm comparator riêng lẻ, không phải thuật toán mặc định.
Best Fit tiếp tục là mặc định. Constructor Portfolio V1 vẫn `NOT_PROMOTED` và không
tham gia UI/canonical registry.

## Hệ quả

Không được claim optimum từ best-observed hoặc lower bound. Không lấy trung bình raw
objective giữa các quy mô. Artifact thiếu/sai checksum fail closed. Việc promote V2
và đánh dấu V1 `superseded` chỉ diễn ra ở checkpoint riêng sau clean rerun.
