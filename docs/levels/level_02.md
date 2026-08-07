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

`extreme_point_ffd` là practical default; `extreme_point_best_fit` là
constructive comparator. Hai solver này có thể bật `container_search` để tìm
trong toàn bộ catalog container vật lý, thay vì chỉ lấy prefix theo số container
được yêu cầu. Flow dùng chung gồm normalization, hard precheck, lower bound và
lazy ranked subset search; sau đó solver vẫn gọi `ExactSupportFeasibilityPolicy`
cho mọi candidate.

Inventory search là opt-in. `milp_big_m`, Hill Climbing, Simulated Annealing và
EMS không hỗ trợ chế độ này trong checkpoint hiện tại và sẽ fail sớm với thông
báo rõ ràng. Khi tắt, hành vi Level 2 hiện hữu không đổi.

Mục tiêu chính thức vẫn là: ít container hơn, sau đó chi phí thấp hơn. Chỉ
nghiệm complete và được independent validator đánh dấu `VALID` mới có objective.
Timeout, incomplete hoặc invalid có `objective=null` cùng diagnostics về
subset, lower bound và unpacked items.

## Quy mô và bằng chứng

Profile 500 và 5.000 container là catalog nghiên cứu generated, có provenance
và fingerprint riêng. Dữ liệu processed/manifest/output của chúng luôn nằm
trong namespace Level 2; không dùng output Level 1 làm input ẩn.

Gate 500 kiểm tra 20/50 item. Gate 5.000 kiểm tra 100 item. Cả hai yêu cầu
deterministic signature và exact-support validation trước khi profile được xem
là evidence thực nghiệm.

## UI inventory và consolidation có giới hạn

UI phân biệt profile smoke 100 kiện với profile nghiên cứu 1.000 kiện. Số kiện
hiển thị phải không vượt số dòng thực của nguồn; request lỗi không được giữ lại
kết quả thành công cũ trên màn hình. Các giới hạn `initial_used_container_count`
và `max_used_container_count` được lưu nguyên vẹn trong `resolved_config.yaml`.

Khi `container_search.consolidation.enabled=true`, pha này coi complete solution
đầu tiên là incumbent và thử dựng lại nghiệm trên
mọi cardinality thấp hơn tới capacity lower bound bằng một số thứ tự kiện
deterministic. Đây là
heuristic bounded, không phải phép chứng minh bất khả thi. Nó không thử dưới cận
tải trọng/thể tích, không thay feasibility policy và không bỏ qua independent
validator Level 2.

Construction, incumbent improvement và validation có budget tách biệt. Một
incumbent hợp lệ luôn được giữ nếu pha cải thiện timeout hoặc sinh candidate
incomplete. Trước construction, request bị từ chối ngay nếu tổng volume hoặc
payload lớn nhất đạt được bằng `max_used_container_count` vẫn không đủ.

Pha container elimination dùng cùng engine với Level 1 nhưng dựng support
closure bắc cầu từ exact-support graph. Nếu một supporter bị phá để xếp lại,
mọi dependent phía trên cũng thuộc neighborhood; engine không được để dependent
ở lại một mình. Thứ tự operator là relocation, closure relocation rồi partial
destroy/repack. Không operator nào được mở container mới.
Partial repack tăng neighborhood theo cấu hình, dùng failed-item evidence để
chọn blocker tại destination và loại candidate trùng bằng deterministic
signature. Failure trong phase này vẫn chỉ là heuristic failure.

Evidence consolidation phân biệt:

- `valid_consolidated`: tìm được nghiệm complete tốt hơn;
- `already_at_lower_bound`: nghiệm đã chạm cận tổng hợp;
- `heuristic_consolidation_failed`: còn khoảng cách với cận nhưng các candidate
  đã thử không tạo được nghiệm complete;
- `candidate_limit` hoặc `consolidation_time_limit`: hết ngân sách nghiên cứu.

Khoảng trống nhìn thấy trong scene 3D không tự chứng minh rằng hai container có
thể hợp nhất. Payload, fixed orientation, non-overlap và exact support vẫn phải
được kiểm tra lại sau khi repack toàn bộ neighborhood.

Inventory orchestration của Level 2 dùng chung type-composition search và global
runtime contract với Level 1. Khác biệt duy nhất ở construction feasibility là
mọi candidate Level 2 tiếp tục qua `ExactSupportFeasibilityPolicy`; nghiệm cuối
vẫn được validator Level 2 tính lại exact union support area. Chế độ unlimited
chỉ bỏ deadline thời gian, không bỏ các search guard và không chứng minh tối ưu.
