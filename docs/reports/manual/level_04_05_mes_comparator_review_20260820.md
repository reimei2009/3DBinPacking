# Review MES Level 4–5

- Quyết định: `ACCEPTED_COMPARATOR_NOT_DEFAULT`.
- Thuật toán mặc định: Extreme Point Best Fit.
- Comparator: Maximal Empty Spaces Best Fit (MES).
- Constructor Portfolio V1: `NOT_PROMOTED`.

## Evidence

Trên 60 bài random của acceptance phân phối, MES so với Best Fit đạt:

| Level | Thắng | Hòa | Thua |
|---|---:|---:|---:|
| Level 4 | 32 | 28 | 0 |
| Level 5 | 32 | 28 | 0 |

Kết quả này chỉ áp dụng cho đúng corpus và fingerprint đã khai báo. Stress, prefix
và các A/B portfolio cho thấy constructor có thể phản ứng khác theo case; vì vậy
không tuyên bố MES tối ưu hoặc tốt hơn trong mọi bài toán. Best Fit cũng chỉ là
baseline mặc định, không phải optimum đã chứng minh.

MES tiếp tục có mặt trên CLI, benchmark và Streamlit như comparator riêng lẻ đã qua
independent validation. Portfolio kết hợp Best Fit + MES không đạt toàn bộ runtime và
deterministic gate Level 5 nên vẫn bị ẩn và không đăng ký làm thuật toán canonical.

File JSON cùng tên khóa SHA-256 của cross-level evidence và capability matrix dùng
cho quyết định này.
