# ADR-0030: Phân biệt inventory container và số container được phép sử dụng

## Trạng thái

Đã chấp nhận cho nền tảng tìm kiếm dùng chung. Chưa kích hoạt làm hành vi mặc định
trên CLI hoặc Streamlit trong checkpoint này.

## Bối cảnh

Tham số số container trước đây có thể bị hiểu đồng thời là số dòng đầu tiên được
đọc từ catalog và số container tối đa solver được phép dùng. Cách hiểu này làm mất
cơ hội chọn một container rẻ hơn hoặc phù hợp hơn nằm ở phía sau catalog.

Inventory thực tế cũng có thể chứa hàng trăm physical instance cùng loại. Liệt kê
power set của toàn bộ inventory là không khả thi, nhưng gộp chúng thành một
container duy nhất lại làm mất số lượng khả dụng.

## Quyết định

1. Inventory là toàn bộ physical container khả dụng trong catalog.
2. `initial_used_container_count` là cardinality bắt đầu tìm kiếm, không phải số
   dòng đầu tiên của catalog.
3. `max_used_container_count` là giới hạn cardinality; chỉ tăng tự động khi
   `automatically_increase_container_count=true`.
4. Các physical container tương đương được nhóm theo geometry, payload, cost và
   constraint profile. Nhóm giữ nguyên danh sách ID và quantity.
5. Hard precheck chỉ kết luận các lỗi có chứng cứ chắc chắn: dữ liệu sai, item
   không vừa bất kỳ orientation/container nào, hoặc tổng volume/payload inventory
   không đủ.
6. Lower bound volume/payload được tính trên inventory hữu hạn, dị thể.
7. Subset được sinh theo cardinality và lazy/bounded. Catalog nhỏ được duyệt chính
   xác theo cardinality; catalog lớn dùng representative type và portfolio có giới
   hạn.
8. Volume buffer chỉ là tín hiệu xếp hạng mềm. Nó không được loại một subset chỉ
   vì subset đó kín hơn ngưỡng mong muốn.

## Hệ quả

- Yêu cầu dùng một container có thể kiểm tra toàn catalog và chọn physical
  container phù hợp/rẻ nhất thay vì mặc định dùng dòng đầu tiên.
- Inventory nhiều container giống nhau được biểu diễn gọn nhưng không mất quantity.
- Chính sách mới có deadline và giới hạn candidate; không tuyên bố đã duyệt hết
  catalog lớn.
- Independent validator vẫn là cổng cuối. Precheck và subset ranking không thay
  thế validation hình học hoặc các ràng buộc theo level.
- CLI/UI hiện tại vẫn giữ semantics cũ cho đến checkpoint promotion riêng, nhằm
  tránh thay đổi âm thầm kết quả Level 1–8.

## Giới hạn

- Chưa có dominance filtering đầy đủ giữa các container type.
- Nhánh inventory lớn là heuristic bounded, không chứng minh subset tối ưu.
- Chưa thay đổi loader CSV: mỗi dòng có `availability=1` vẫn là một physical
  instance; quantity được suy ra bằng số dòng tương đương.
