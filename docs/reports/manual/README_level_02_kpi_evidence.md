# Evidence KPI/MES/repair — Level 2

`build_level2_kpi_acceptance_report.py` chỉ tổng hợp benchmark run được truyền
tường minh. Nó không tự tìm run mới nhất và không chạy lại solver.

Ví dụ với ba run đã có:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_level2_kpi_acceptance_report.py `
  --control-run outputs\level_02\runs\<control_run> `
  --kpi-run outputs\level_02\runs\<kpi_run_100_300> `
  --repair-run outputs\level_02\runs\<repair_run> `
  --output-dir docs\reports\manual
```

Sau gate KPI 500, truyền thêm `--kpi-run outputs\level_02\runs\<kpi_run_500>`.
Script kiểm tra checksum items/container và checksum danh sách item được chọn trước
khi so sánh. `WIN/TIE/LOSS` chỉ dựa trên objective chính thức:
`(used_container_count, total_container_cost)`.

`diagnostic_secondary_search_score` là KPI quan sát được tính từ placements cuối
cùng đã qua independent validation. Nó không được dùng để đánh đổi thêm container
hoặc chi phí. `official_secondary_search_score` chỉ xuất hiện khi secondary KPI
được bật thật sự trong configuration selection.
