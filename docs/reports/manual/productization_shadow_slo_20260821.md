# Productization Shadow SLO — 2026-08-21

## Kết luận

Trạng thái chính thức: **SHADOW_NOT_READY**.

Benchmark nghiệp vụ giả lập đạt 162/162 lượt `VALID`, không timeout, không invalid
và 54/54 nhóm deterministic. Gate còn thiếu duy nhất là thời gian phản hồi UI:
p95 warm Streamlit rerun là **3,099 giây**, cao hơn giới hạn **2 giây**.

Kết quả này không bao gồm solver, browser paint hoặc network. Không có outlier nào
bị loại. Cold start 0,665 giây được báo riêng và không tham gia gate.

## Phép đo UI

- Metric: `warm_streamlit_rerun_v1`.
- Profile: Level 2, nguồn 1.000 kiện / 500 container.
- 3 warmup bị loại khỏi thống kê; 30 mẫu chính thức được giữ nguyên.
- Mỗi mẫu đổi số kiện 100 ↔ 101 và đo toàn bộ server-side rerun.
- p50: 2,791 giây; p95: 3,099 giây; min–max: 2,205–3,537 giây.
- Source commit: `7d241ef76a6f42b707c7a27fe78d4ff72a363ac1`; `git_dirty=false`.

## Ý nghĩa

Core solver/validator đã qua Shadow gate, nhưng UI chưa đạt SLO ứng viên. Chưa được
tuyên bố production-ready. Bước cải thiện UI phải được profiling riêng; không nới
ngưỡng hoặc bỏ mẫu để làm report chuyển sang PASS.

Checksums đầy đủ và 30 mẫu thô nằm trong file JSON đi kèm.
