# ADR-0038 — Tìm kiếm inventory theo thành phần loại container

## Trạng thái

Đã chấp nhận cho runtime inventory-aware của Level 1 và Level 2.

## Bối cảnh

Catalog nghiên cứu có thể chứa hàng trăm physical container nhưng chỉ có một số
ít loại tương đương. Cách sinh subset theo physical ID từng thử nhiều phương án
khác nhau về ID nhưng giống hệt geometry, payload và cost. Việc này tiêu tốn
candidate budget mà không tạo thêm lựa chọn packing có ý nghĩa.

Ngoài ra, một cardinality thấp có thể dùng gần hết deadline trước khi solver thử
cardinality cao hơn. Trạng thái `INFEASIBLE_HEURISTIC` vì vậy dễ bị hiểu sai là
bằng chứng bài toán vô nghiệm.

## Quyết định

1. Catalog lớn được nhóm theo type tương đương canonical.
2. Candidate search dùng `ContainerTypeComposition`, tức số lượng của từng type.
3. Physical IDs chỉ được materialize deterministic ngay trước construction.
4. Mỗi cardinality được thử một capacity anchor trước; sau đó mới quay lại
   portfolio được xếp hạng theo cost và capacity slack.
5. Construction có portfolio item order bounded dùng chung cho FFD và Best Fit.
6. `container_search.time_limit_seconds` là deadline chung. Giá trị `null` chỉ
   bỏ deadline thời gian; composition cap, candidate cap, item-order cap và giới
   hạn số container vẫn hoạt động.
7. Independent validator của từng level vẫn là gate cuối cùng. Chỉ nghiệm
   complete và `VALID` mới có objective chính thức.

## Hệ quả

- Không còn lặp hàng tỷ tổ hợp physical ID tương đương trong search thực tế.
- Search bounded có cơ hội thử cardinality đủ lớn trước khi hết thời gian.
- Chế độ không giới hạn vẫn kết thúc khi không gian heuristic bounded đã hết;
  nó không phải exhaustive search và không chứng minh tối ưu.
- Level 1 và Level 2 tái sử dụng cùng orchestration; exact-support policy của
  Level 2 không bị sao chép hoặc làm yếu.

## Giới hạn

- Portfolio type-composition là heuristic, không duyệt toàn bộ tổ hợp type.
- Nghiệm đầu tiên ở một cardinality cao hơn có thể chưa phải nghiệm tốt nhất
  trong toàn bộ không gian bounded.
- Chế độ không giới hạn chỉ nên dùng nghiên cứu cục bộ. Web deploy phải bật rõ
  `ALLOW_UNBOUNDED_INVENTORY_SEARCH=true` nếu muốn expose tùy chọn này.
