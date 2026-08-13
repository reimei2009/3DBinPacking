# Level 2 — Ràng buộc hỗ trợ hình học chính xác

Level 2 kế thừa nguyên vẹn geometry, assignment, payload và thứ tự objective
lexicographic của Level 1. Bổ sung của Level 2 là: mỗi kiện phải nằm trên sàn
container hoặc được đỡ bởi các mặt trên ở ngay bên dưới.

## Ràng buộc đang hoạt động

- orientation cố định;
- boundary, non-overlap và payload;
- floor contact;
- tỷ lệ diện tích đáy được hỗ trợ tối thiểu;
- tâm hình học của đáy phải nằm trong hợp của các vùng tiếp xúc;
- validator độc lập tính lại chính xác hợp diện tích các hình chữ nhật tiếp xúc.

MILP dùng lưới cấu hình được để tham chiếu; validation exact union area là nguồn
sự thật cuối cùng. Rotation, stackability, load-bearing, nesting, COG,
loading/unloading order và ổn định vật lý đầy đủ chưa được kích hoạt.

Nghiệm hợp lệ chỉ được mô tả là:

> Nghiệm khả thi về hình học, tải trọng và hỗ trợ đáy theo giả định Level 2.

## Solver và inventory-aware search

`extreme_point_best_fit` là solver practical được khuyến nghị khi ưu tiên chất
lượng nghiệm; `extreme_point_ffd` là comparator nhanh. Không có fallback ngầm
giữa hai thuật toán. Hai solver này có thể bật `container_search` để tìm
trong toàn bộ catalog container vật lý, thay vì chỉ lấy prefix theo số container
được yêu cầu. Flow dùng chung gồm normalization, hard precheck, lower bound và
lazy ranked subset search; sau đó solver vẫn gọi `ExactSupportFeasibilityPolicy`
cho mọi candidate.

Inventory search là opt-in. `extreme_point_best_fit`, `extreme_point_ffd` và
`maximal_space_best_fit` dùng chung orchestration này. MES là research
comparator CLI/benchmark; chưa có control inventory riêng trên UI.
`milp_big_m`, Hill Climbing và Simulated Annealing không hỗ trợ chế độ này trong
checkpoint hiện tại và sẽ fail sớm với thông báo rõ ràng. Khi tắt, hành vi
Level 2 hiện hữu không đổi.

Mục tiêu chính thức vẫn là: ít container hơn, sau đó chi phí thấp hơn. Chỉ
nghiệm complete và được independent validator đánh dấu `VALID` mới có objective.
Timeout, incomplete hoặc invalid có `objective=null` cùng diagnostics về
subset, lower bound và unpacked items.

Tuple `(used_container_count, total_container_cost)` là objective chính thức.
Scalar mã hóa legacy chỉ được giữ để tương thích artifact và không dùng để so
sánh chéo catalog.

### KPI phụ không thay objective

Config `container_search.secondary_search_score.enabled` mặc định `false`.
Khi bật, candidate complete và independently `VALID` có cùng objective chính
thức được phân xử tiếp bằng:

```text
(-utilization_concentration,
 internal_void_ratio,
 -minimum_support_margin,
 placement_signature)
```

KPI phụ không được phép đổi thêm container lấy compactness, không được đánh đổi
chi phí và không biến support thành soft constraint. Construction có thể chạy
hết bounded item-order portfolio tại cardinality đầu tiên đã có incumbent để
tìm tie-break tốt hơn; không tiếp tục lên cardinality cao hơn. Quyết định kiến
trúc và công thức chuẩn hóa nằm tại
[ADR-0042](../decisions/ADR-0042-kpi-phu-va-mes-inventory-level-2.md).

MES inventory tái sử dụng đúng engine MES canonical. Seed partial-repack được
dựng lại theo thứ tự deterministic và phải qua `ExactSupportFeasibilityPolicy`
trước khi xếp item còn lại. Candidate cuối vẫn qua independent validator Level
2 và final pipeline tiếp tục validate lại từ raw input.

## Quy mô và bằng chứng

### Benchmark canonical

Benchmark nội bộ chính thức dùng cùng nguồn 1.000 kiện / 500 physical container /
10 loại C1–C10. Protocol constructor gồm 24 case ở các mức 20, 50, 100, 200,
300 và 500 kiện; Best Fit là baseline, FFD và MES là comparator. Hai repeat tạo
144 execution để kiểm tra deterministic. Repair tắt trong protocol này và được
đánh giá bằng A/B riêng.

Chi tiết, artifact và lệnh chạy nằm tại
[Benchmark canonical Level 2](../benchmarks/level_02_benchmark_v2.md). MPV tiếp tục
là evidence học thuật riêng và không được gộp với generated canonical.

Evidence canonical phát hành ngày 2026-08-13 nằm tại
[report benchmark Level 2](../reports/manual/level_02_canonical_benchmark_20260813.md).
Report xác nhận 24 bài, 144 lượt chạy và 144 nghiệm `VALID`; Best Fit vẫn chỉ là
baseline đối chiếu, không phải optimum đã chứng minh.

Benchmark V2 phân tầng đang ở trạng thái ứng viên nghiên cứu. Nó giữ nguyên sáu quy
mô nhưng mở rộng thành 60 bài random, 18 bài stress và 6 bài prefix, mỗi bài chạy ba
thuật toán qua ba repeat. Ba tầng không bị gộp thống kê: random dùng kết luận phân
phối, stress dùng kiểm tra sức chịu đựng, prefix dùng phát hiện hồi quy. V1 tiếp tục
là canonical cho đến khi V2 hoàn thành đủ 84 bài/756 lượt và qua promotion gate.

Gate V2 ngày 2026-08-13 đã đạt đủ 84 bài, 756 lượt `VALID` và 252/252 nhóm
deterministic. Tầng random có 3 thắng/57 hòa/0 thua của FFD và 6 thắng/53 hòa/1
thua của MES khi so với Best Fit. Stress và prefix vẫn được báo riêng. Evidence nằm
tại `docs/reports/manual/level_02_stratified_benchmark_v2_20260813.{json,md}`;
việc đổi registry canonical là checkpoint quản trị riêng, không rewrite V1.

Sau khi cả ba tầng V2 trả `PASS`, quy trình
[profiling runtime Level 2](../benchmarks/level_02_runtime_profiling.md) đo phase từ
telemetry chính thức và dùng `cProfile` trên một tập chẩn đoán nhỏ. Run profiling
không tham gia objective, WIN/TIE/LOSS hoặc evidence canonical.

Profile 500 và 5.000 container là catalog nghiên cứu generated, có provenance
và fingerprint riêng. Dữ liệu processed/manifest/output của chúng luôn nằm
trong namespace Level 2; không dùng output Level 1 làm input ẩn.

Gate 500 kiểm tra 20/50 item. Gate 5.000 kiểm tra 100 item. Cả hai yêu cầu
deterministic signature và exact-support validation trước khi profile được xem
là evidence thực nghiệm.

Gate nối liền 20–300 item dùng cùng nguồn 1.000 kiện và catalog 500 container:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_02\benchmarks\inventory_scale_20_300_manual.yaml
```

Suite chạy Best Fit primary và FFD comparator hai lần trên từng quy mô. Chỉ
row complete, independently `VALID` và có official objective mới được tham gia
aggregate/ranking; placement signature giữa hai repeat phải giống nhau.

Gate nội bộ ngày 2026-08-10 đạt 633 test pass. Trên 300 kiện/500 container,
Best Fit dùng 11 container với chi phí 22.000 trong khoảng 13,13 giây; FFD dùng
12 container với chi phí 24.000 trong khoảng 12,66 giây. Full suite gần nhất
trước khi phát hành evidence MPV đạt 695 test pass.

Corpus ngoài dùng view fixed-orientation và exact support theo tài liệu
[MPV Level 2](../datasets/mpv_fixed_orientation_level2.md). Run acceptance ngày
2026-08-12 có đúng 27 case, hai thuật toán, hai repeat và 108/108 execution
independently `VALID`. Mọi cặp case–algorithm deterministic; Best Fit so với FFD
đạt `1 WIN / 25 TIE / 1 LOSS`. Reference heuristic mang nhãn `best_observed`,
chỉ có nghĩa là nghiệm tốt nhất quan sát được trên cùng input fingerprint trong
run này, không phải best-known MPV gốc và không chứng minh tối ưu.

Evidence phát hành tại
[Nghiệm thu Level 2 ngày 2026-08-12](../reports/manual/level_02_acceptance_20260812.md)
có trạng thái `PASS`. Level 2 được đóng theo contract hiện tại và cho phép lập
kế hoạch promotion Level 3 riêng; checkpoint này không thay đổi runtime Level 3.

## UI inventory và consolidation có giới hạn

UI phân biệt profile smoke 100 kiện với profile nghiên cứu 1.000 kiện. Số kiện
hiển thị phải không vượt số dòng thực của nguồn; request lỗi không được giữ lại
kết quả thành công cũ trên màn hình. Các giới hạn `initial_used_container_count`
và `max_used_container_count` được lưu nguyên vẹn trong `resolved_config.yaml`.

Với Best Fit/FFD inventory-aware, UI có checkbox repair riêng và các budget
3/10/30 giây hoặc tùy chỉnh. Checkbox mặc định theo profile nhưng người dùng có
thể tắt để ưu tiên runtime. Khi inventory search tắt, UI cũng ép consolidation
và container elimination tắt; không có repair ngầm. Preview hiển thị đồng thời
global deadline, repair budget và validation reserve.

Khi `container_search.consolidation.enabled=true`, pha này coi complete solution
đầu tiên là incumbent và thử giảm tuần tự đúng một container. Chỉ sau khi
cardinality `incumbent - 1` tạo nghiệm complete, independently `VALID`, engine
mới thử `incumbent - 2`; một cardinality thất bại sẽ dừng nhánh rebuild thay vì
chia đều budget xuống tận capacity lower bound. Đây là
heuristic bounded, không phải phép chứng minh bất khả thi. Nó không thử dưới cận
tải trọng/thể tích, không thay feasibility policy và không bỏ qua independent
validator Level 2.

Construction, incumbent improvement và validation có budget tách biệt. Một
incumbent hợp lệ luôn được giữ nếu pha cải thiện timeout hoặc sinh candidate
incomplete. Trước construction, request bị từ chối ngay nếu tổng volume hoặc
payload lớn nhất đạt được bằng `max_used_container_count` vẫn không đủ.

Với inventory lớn, construction dùng pha feasibility-first trước khi tối ưu.
Cardinality bắt đầu tại capacity lower bound rồi tăng theo midpoint tới giới
hạn request; mỗi cardinality chỉ thử capacity-rich anchor và cost-ranked
candidate. Ví dụ lower bound 9 và cap 15 tạo ladder `9 → 12 → 14 → 15`.
Ngay khi có candidate complete và qua independent validator, candidate đó trở
thành incumbent; consolidation sau đó mới thử giảm container và chi phí.

Pha container elimination dùng cùng engine với Level 1 nhưng dựng support
closure bắc cầu từ exact-support graph. Nếu một supporter bị phá để xếp lại,
mọi dependent phía trên cũng thuộc neighborhood; engine không được để dependent
ở lại một mình. Thứ tự operator là relocation, closure relocation rồi partial
destroy/repack. Không operator nào được mở container mới.
Partial repack tăng neighborhood theo cấu hình và xét cluster 1–3 destination.
Shortlist là một portfolio bounded gồm destination có extreme point sẵn, dư tải
trọng, dư thể tích và destination cần phá blocker. Beam lấy quota theo từng kích
thước cluster, nên cluster hai hoặc ba đích không bị cluster một đích chiếm hết.
Planner dùng failed-item evidence để chọn blocker, repack toàn bộ target cùng
support closure cần thiết và loại candidate trùng bằng deterministic signature.
Failure trong phase này vẫn chỉ là heuristic failure.

Budget improvement được chia thành local repair và full rebuild bằng
`improvement_phase_time_fractions` (mặc định `0.60/0.40`). Local phase kết thúc
sớm thì phần thời gian chưa dùng vẫn có thể chuyển cho rebuild; candidate trả về
sau deadline không được thay validated incumbent.

Evidence consolidation phân biệt:

- `valid_consolidated`: tìm được nghiệm complete tốt hơn;
- `already_at_lower_bound`: nghiệm đã chạm cận tổng hợp;
- `heuristic_consolidation_failed`: còn khoảng cách với cận nhưng các candidate
  đã thử không tạo được nghiệm complete;
- `candidate_limit` hoặc `consolidation_time_limit`: hết ngân sách nghiên cứu.

Khoảng trống nhìn thấy trong scene 3D không tự chứng minh rằng hai container có
thể hợp nhất. Payload, fixed orientation, non-overlap và exact support vẫn phải
được kiểm tra lại sau khi repack toàn bộ neighborhood. UI báo thêm mức sử dụng
volume/payload lạc quan bắt buộc tại aggregate lower bound và lý do target chưa
đóng được (`payload`, `geometry`, `support`, `deadline` hoặc candidate limit).

Inventory orchestration của Level 2 dùng chung type-composition search và global
runtime contract với Level 1. Khác biệt duy nhất ở construction feasibility là
mọi candidate Level 2 tiếp tục qua `ExactSupportFeasibilityPolicy`; nghiệm cuối
vẫn được validator Level 2 tính lại exact union support area. Chế độ unlimited
chỉ bỏ deadline thời gian, không bỏ các search guard và không chứng minh tối ưu.

Controlled A/B capacity-aware consolidation được chạy thủ công bằng:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_02\benchmarks\capacity_aware_consolidation_ab_manual.yaml
```

Suite dùng cùng nguồn 1.000 kiện và catalog 500 container, hai repeat cho mỗi
profile 100/300/500 item (prefix và stable-random seed 101). Planner mới chỉ
được giữ nếu có ít nhất một objective `WIN`, không có `LOSS`, deterministic và
mọi nghiệm thành công independently `VALID` trong global budget 120 giây.
## Ghi chú UI benchmark và nguồn nghiên cứu lớn

Benchmark UI dùng atomic request snapshot. Không có live preview dựa trên browser
draft hoặc Session State cũ: sau khi submit, cùng một snapshot được dùng cho capacity
precheck, solver execution, manifest và header kết quả. Nếu người dùng chọn bắt đầu
1 và tối đa 50 container thì mọi artifact phải giữ đúng 1/50; nguồn chỉ có 5 physical
container sẽ không cho nhập giới hạn 50.

View nghiên cứu `level_02_solver_research_i20000_f5000_v1` được materialize từ prefix
20.000 item của corpus pipeline 100.000 item và giữ toàn bộ 5.000 physical container.
View có manifest/checksum và capacity qualification riêng; nó không thay đổi usage
class của corpus nguồn. Streamlit chỉ hiển thị view sau gate thủ công tại các quy mô
1.000, 5.000, 10.000 và 12.389 item tạo `web_qualification.json` khớp checksum.
