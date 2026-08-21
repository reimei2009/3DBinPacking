# Productization readiness baseline — 2026-08-21

## Kết luận

Trạng thái hiện tại là **SHADOW_NOT_READY**. Project đã đủ nền tảng để chạy
shadow evaluation có kiểm soát, nhưng UI p95 chưa đạt gate 2 giây.

## Gate đã đạt trong checkpoint

- Full regression: `841 passed`.
- Targeted productization/UI/governance: `101 passed`.
- Company-like population materialize deterministic: 1.000 kiện/500 container.
- E2E Level 2 nhỏ: 20 kiện, Best Fit, `FEASIBLE + VALID`, dùng 1 container.
- CI ép import từ `src` của checkout/worktree hiện tại.
- Corpus contract phân loại đầy đủ cost/load-bearing/safety clearance/measurement
  error và ghi rõ đây là `synthetic_calibrated_shadow`.

## Evidence sau checkpoint

- Shadow benchmark đã có 162/162 lượt `VALID` và deterministic.
- UI response có 30 mẫu sạch: p95 3,099 giây, vượt gate 2 giây.
- Repair early-stop A/B đạt 48/48 lượt `VALID`, nhưng quyết định là
  `NOT_PROMOTED` vì 2 cặp làm xấu official objective.
- Chưa có cost, vật liệu, safety clearance hoặc sai số đo do doanh nghiệp cung cấp.

Vì vậy evaluator trả `SHADOW_NOT_READY`; không loại outlier hoặc nới SLO.

## Quyết định caching

Không triển khai Contact/Support Cache V3. Chỉ mở lại hướng cache nếu profiling trên
dữ liệu mới đồng thời chứng minh profile share ≥30%, hit-rate dự kiến ≥40% và wall
runtime có khả năng giảm ≥20%.

## Lệnh evidence thủ công kế tiếp

```powershell
python scripts\measure_ui_response.py `
  --level level_02 `
  --profile items_1000_fleet_500_t10 `
  --warmups 3 `
  --samples 30

python scripts\evaluate_productization_shadow.py `
  --run-dir outputs\level_02\runs\<run_id> `
  --ui-evidence-run-dir outputs\level_02\runs\<ui-response-run-id>

python scripts\run_benchmark_corpus.py `
  --corpus config\level_02\benchmarks\repair_signal_diagnostic_manual.yaml
```

Chỉ nghiệm complete và independently `VALID` được có official objective. Report
shadow không phải chứng nhận an toàn cơ học hay cam kết SLA production.
