# Productization readiness baseline — 2026-08-21

## Kết luận

Trạng thái hiện tại là **PENDING_SHADOW_EVIDENCE**. Project đã đủ nền tảng để chạy
shadow evaluation có kiểm soát, nhưng chưa đủ evidence để tuyên bố production-ready.

## Gate đã đạt trong checkpoint

- Full regression: `841 passed`.
- Targeted productization/UI/governance: `101 passed`.
- Company-like population materialize deterministic: 1.000 kiện/500 container.
- E2E Level 2 nhỏ: 20 kiện, Best Fit, `FEASIBLE + VALID`, dùng 1 container.
- CI ép import từ `src` của checkout/worktree hiện tại.
- Corpus contract phân loại đầy đủ cost/load-bearing/safety clearance/measurement
  error và ghi rõ đây là `synthetic_calibrated_shadow`.

## Evidence chưa chạy

- Shadow benchmark 162 lượt chưa được chạy trong checkpoint code này.
- UI response p95 chưa có phép đo đủ mẫu.
- Repair early-stop A/B 48 lượt chưa được chạy.
- Chưa có cost, vật liệu, safety clearance hoặc sai số đo do doanh nghiệp cung cấp.

Vì vậy evaluator phải trả `SHADOW_NOT_READY` nếu thiếu artifact hoặc UI latency.

## Quyết định caching

Không triển khai Contact/Support Cache V3. Chỉ mở lại hướng cache nếu profiling trên
dữ liệu mới đồng thời chứng minh profile share ≥30%, hit-rate dự kiến ≥40% và wall
runtime có khả năng giảm ≥20%.

## Lệnh evidence thủ công kế tiếp

```powershell
python scripts\run_benchmark_corpus.py `
  --corpus config\level_02\benchmarks\company_like_shadow_manual.yaml

python scripts\evaluate_productization_shadow.py `
  --run-dir outputs\level_02\runs\<run_id> `
  --ui-response-p95-seconds <giá-trị-đo>

python scripts\run_benchmark_corpus.py `
  --corpus config\level_02\benchmarks\repair_early_stop_ab_manual.yaml
```

Chỉ nghiệm complete và independently `VALID` được có official objective. Report
shadow không phải chứng nhận an toàn cơ học hay cam kết SLA production.
