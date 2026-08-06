# ADR-0033: Profile UI cho inventory container quy mô lớn ở Level 1

## Bối cảnh

Catalog 500 và 5.000 container đã qua scale gate bằng CLI/config. Nếu UI chỉ
hiển thị một ô số container trên catalog inline C1--C5, người dùng có thể hiểu
nhầm rằng số đó là quy mô kho hoặc rằng solver chỉ đọc prefix container.

## Quyết định

Level 1 dùng registry YAML `config/level_01/web_inventory_profiles.yaml` để
chọn catalog versioned. UI đọc một service tổng hợp inventory chỉ-đọc, hiển thị
số physical container, số type tương đương và bảng gộp theo type; UI không tải
bảng 5.000 dòng.

Ba biến được giữ tách biệt:

\[
|K_{available}|,\qquad k_{start},\qquad M_{max}.
\]

Trong đó \(M_{max}\) là budget số container được phép dùng. Candidate subset
được sinh lazy theo cardinality và bị giới hạn bởi deadline/candidate budget;
đây không phải enumeration toàn bộ power set.

Catalog generated bị thiếu phải trả thông báo có lệnh generate. Không được
fallback ngầm sang catalog cơ bản vì điều đó làm thay đổi điều kiện thí nghiệm.

UI phải phân biệt nhãn loại do nguồn dữ liệu khai báo với type tương đương
canonical (`CT-...`) dùng trong thuật toán. Mỗi catalog physical có một
`inventory_fingerprint` deterministic, được hiển thị ở preview và lưu vào run để
không so sánh nhầm hai kho có cùng số lượng nhưng khác container.

## Hệ quả

- Best Fit và FFD Level 1 có thể được demo với inventory 500/5.000 container.
- Catalog lớn vẫn là bounded heuristic, không phải exact subset optimization.
- Whitelist ID container là ràng buộc vận hành khác với usage budget và chưa
  thuộc checkpoint này.
- Level 2--8 không bị thay đổi hoặc hiển thị thêm controls inventory trong ADR
  này.
