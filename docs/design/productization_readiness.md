# Productization readiness và shadow evaluation

## Hai loại bằng chứng

- **Regression kỹ thuật:** corpus 1.000 kiện/500 container hiện có, dùng để phát hiện
  thay đổi solver và validator.
- **Company-like shadow:** dữ liệu synthetic được hiệu chỉnh bằng các giả định logistics
  đã khai báo. Nó giúp thử quy trình gần nghiệp vụ hơn nhưng không phải dữ liệu công ty.

Contract authoritative nằm tại
`config/productization/company_like_shadow_v1.yaml`. Dữ liệu được sinh từ
`config/synthetic/company_like_shadow_v1.yaml`; output tái sinh nằm trong
`data/interim/productization/` và không commit.

## Quy trình

```text
Contract + generation profile
  → materialize deterministic population
  → benchmark ghép cặp Best Fit / FFD / MES
  → independent validation
  → SLO evaluator fail-closed
  → shadow report (không phải production certificate)
```

Các case gồm 100, 300 và 500 kiện; mỗi quy mô có random và ba nhóm stress: cồng
kềnh, nặng và áp lực tải trọng. Ba thuật toán trong cùng case phải dùng cùng input
fingerprint. Không lấy trung bình raw container count/cost xuyên quy mô.

## Production candidate SLO

- 100% nghiệm công bố phải `VALID` qua validator độc lập.
- Failure/timeout không được mang official objective.
- Runtime p50/p95, peak RSS và UI response p95 phải có đủ mẫu.
- Repeat phải deterministic theo objective và placement signature.
- Best Fit là baseline, MES/FFD là comparator; không thuật toán nào được gọi là
  optimum nếu thiếu exact proof.

## Lệnh vận hành

```powershell
python scripts\prepare_company_shadow_corpus.py
python scripts\run_benchmark_corpus.py `
  --corpus config\level_02\benchmarks\company_like_shadow_manual.yaml
python scripts\evaluate_productization_shadow.py `
  --run-dir outputs\level_02\runs\<run_id> `
  --ui-response-p95-seconds <giá-trị-đo>
```

Kiểm thử từ một Git worktree phải chạy qua:

```powershell
python scripts\run_quality_gate.py --scope all
```

Script xác minh package được import từ chính `src` của worktree hiện tại trước khi
chạy pytest.

## Giới hạn

Chi phí là tương đối; load-bearing là synthetic; safety clearance và measurement
error đang `unsupported`. Vì vậy kết quả chỉ phục vụ shadow evaluation, không phải
chứng nhận an toàn, quyết định vận hành tự động hoặc production SLA.
