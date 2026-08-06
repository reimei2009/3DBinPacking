# Data contract Level 3 — Orientation ngang

Trạng thái: **đang được runtime, solver và independent validator Level 3 sử dụng**.

## Field nguồn

| Field | Trạng thái | Quy tắc |
| --- | --- | --- |
| `length_mm`, `width_mm`, `height_mm` | used | Kích thước gốc theo mm |
| `weight_kg` | used | Không đổi khi xoay |
| `forced_orientation` | preserved, inactive | Chưa map vì semantics nguồn chưa được xác minh |
| `stackability_code`, `max_stackability`, `nesting_height_mm` | preserved, inactive | Thuộc contract level sau |

Level 3 chỉ xoay trong mặt phẳng ngang và giữ nguyên trục `z`. Stackability là
contract độc lập và không được suy ra từ orientation.

## Field chuẩn hóa

| Field | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `orientation_profile_id` | string | Profile khai báo nguồn của tập hướng |
| `allowed_orientation_codes` | JSON array | Tập con đã loại trùng của `XYZ`, `YXZ` |
| `orientation_data_status` | string | Trạng thái provenance của orientation |

`allowed_orientation_codes` là input canonical cho solver và validator.
Solver không được đọc `forced_orientation` trực tiếp.

## Validation

- dimensions và weight dương;
- mỗi item có ít nhất một orientation;
- code duy nhất và thuộc `{XYZ, YXZ}`;
- loại `YXZ` khi tạo cùng kích thước với `XYZ`;
- orientation trong output thuộc tập được phép của item;
- kích thước output khớp chính xác orientation đã chọn.

Raw data không bị sửa; mọi mapping nguồn được version hóa trong config và
input snapshot của run.
