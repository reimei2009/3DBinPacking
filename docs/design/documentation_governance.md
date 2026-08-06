# Quản trị tài liệu

## Mục tiêu

Giữ tài liệu ngắn, đúng trạng thái runtime và có một nguồn sự thật rõ ràng.
Tuổi của file không phải lý do đủ để xóa; một file chỉ được loại bỏ khi đã có
tài liệu thay thế hoàn chỉnh và không còn consumer cần cho tái lập.

## Phân loại

- **Canonical:** `docs/levels/level_XX.md`, index và hướng dẫn vận hành hiện
  hành. Phải được cập nhật khi contract hoặc exposure thay đổi.
- **Specification:** chi tiết data/model/acceptance. Không được tự công bố
  maturity khác tài liệu level canonical.
- **Decision history:** ADR. Giữ lịch sử; khi bị thay thế, ghi rõ
  `superseded_by` thay vì xóa.
- **Evidence:** chỉ giữ baseline hoặc milestone có provenance, checksum và gate
  rõ ràng. Output thô không được chép vào docs.
- **Archive:** chỉ tồn tại tạm thời trong lúc migration. Git đã lưu lịch sử nên
  bản sao superseded không được giữ vô thời hạn.

## Nguồn sự thật

- Registry Python: level và algorithm nào thực thi được.
- `config/common/capability_matrix.yaml`: maturity, role và exposure theo từng
  cặp level–algorithm.
- `docs/levels/level_XX.md`: ý nghĩa, ràng buộc và giới hạn của level.
- Run manifest: provenance của một lần chạy cụ thể.

## Quy trình cập nhật hoặc xóa

1. Tìm toàn bộ reference và consumer của file.
2. Chỉ ra tài liệu thay thế và nội dung cần bảo toàn.
3. Trình bày batch gồm đường dẫn, lý do, hành động và rủi ro.
4. Nhận xác nhận rõ ràng của người dùng.
5. Cập nhật link, test documentation health và chạy `git diff --check`.
6. Không trộn cleanup tài liệu với output, cache hoặc generated data.

Mỗi batch xóa mới đều phải xin phép; quyền xóa một batch không được suy rộng
cho batch sau.
## Ngôn ngữ

Tài liệu mới và tài liệu cũ được chỉnh sửa đáng kể phải viết bằng tiếng Việt.
Identifier, schema key, mathematical symbol và thuật ngữ kỹ thuật ổn định có
thể giữ tiếng Anh để khớp code.
