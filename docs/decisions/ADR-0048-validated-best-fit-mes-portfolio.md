# ADR-0048 — Portfolio Best Fit và MES có kiểm định

## Trạng thái

Candidate — chỉ được promote sau benchmark Level 4–5.

## Bối cảnh

MES thường nhanh hơn và tạo nhiều nghiệm dùng ít container hơn Best Fit, nhưng vẫn
thua Best Fit ở một số bài stress. Hai vòng tối ưu contact/support index không đạt
gate hiệu năng, còn candidate enumeration chỉ chiếm khoảng 10–11% construction.

## Quyết định

Thử một portfolio bounded gồm Extreme Point Best Fit và Maximal Empty Spaces Best
Fit. Best Fit chạy trước với 65% cửa sổ construction được bảo vệ; MES dùng phần
thời gian còn lại. Thời gian không dùng hết được chuyển cho constructor sau.

Mỗi candidate hoàn chỉnh phải qua validator độc lập. `ValidatedIncumbentStore` chỉ
giữ nghiệm tốt hơn theo objective chính thức `(số container, tổng chi phí)`. Candidate
invalid, incomplete hoặc timeout không thể thay incumbent.

Checkpoint này không hỗ trợ repair và chưa hiển thị trên Streamlit. FFD tiếp tục là
comparator nhanh, không thuộc portfolio.

## Hệ quả

- Chất lượng không thể kém hơn một child candidate hợp lệ đã hoàn thành.
- Runtime dự kiến tăng khoảng 1,5–1,8 lần so với Best Fit riêng.
- Portfolio dùng chung precheck, inventory, deadline, validation reserve và output;
  không ghép hai experiment độc lập.
- Chỉ promote nếu cả Level 4 và Level 5 đạt acceptance đã khai báo.
