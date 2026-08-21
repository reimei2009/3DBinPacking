# Thiết kế benchmark

## Ba tầng tổng hợp

Benchmark phân biệt rõ một lượt chạy, một bài kiểm tra và phân phối nhiều bài:

1. Lượt chạy là một thuật toán trên một input và một repeat.
2. Một bài kiểm tra chỉ tổng hợp các lượt có cùng `case_id`, input fingerprint,
   thuật toán và seed.
3. Nhiều bài kiểm tra chỉ dùng metric ghép cặp hoặc chuẩn hóa. Không lấy trung
   bình raw số container, chi phí hoặc encoded objective giữa các quy mô.

`case_id` là định danh canonical; `scenario_id` chỉ là fallback khi đọc artifact
lịch sử. Runtime chính trên dashboard là wall runtime của toàn pipeline. p95 chỉ
được công bố khi nhóm có ít nhất 10 lượt chạy.

Benchmark runner chỉ lấy các cặp level/thuật toán đã có implementation từ
registry. Mỗi ô trong ma trận là một experiment bất biến, có input, solution,
validator, metrics và manifest riêng. Aggregate cũng là một run cô lập theo
level; `manifest.json` của nó tham chiếu toàn bộ source run.

`benchmark/results.csv` là bảng thô gồm seed hiệu lực, repeat đo thời gian,
quality metrics và placement signature canonical. `benchmark/summary.csv` cùng
`summary.json` ghi số run/seed, success rate, thống kê chất lượng, compactness,
runtime và số nghiệm khác nhau. Một case chỉ thành công khi thuật toán trả nghiệm
complete và independent validator xác nhận hợp lệ. `OPTIMAL` và `FEASIBLE` luôn
được phân biệt.

Các corpus mới tạo thêm `case_algorithm_summary.csv` và `case_differences.csv`.
Bảng thứ nhất chỉ gộp repeat trong cùng `case_id`, fingerprint, thuật toán và seed.
Bảng thứ hai chỉ giữ các bài có official objective khác nhau giữa các thuật toán.
Thống kê xuyên nhiều bài dùng trung vị cùng khoảng nhỏ nhất–lớn nhất của gap đã chuẩn
hóa theo lower bound; tuyệt đối không lấy trung bình raw số container, chi phí hoặc
encoded objective giữa các quy mô.

## Fingerprint và điều kiện đưa vào thống kê

`input_fingerprint` bao phủ item selection, toàn bộ container catalog, resolved
contract/rules file, selection seed và generation manifest. Tham số riêng của
thuật toán nằm trong `experiment_fingerprint`; vì vậy hai thuật toán trên cùng
instance có cùng input fingerprint nhưng experiment fingerprint khác nhau.

Chỉ row có solver status thành công và independent validation `VALID` mới được
đưa vào Pareto, ranking, best-observed và aggregate chất lượng. Row thất bại nhưng
còn objective bị benchmark runner reject. Ranking chính thức dùng tuple số
container rồi tổng chi phí; `objective_value` scalar chỉ là trường tương thích.

Telemetry benchmark gồm runtime thuật toán, pipeline, reporting, peak RSS,
candidate/rejection count, subset count, repair count và termination reason khi
nguồn metadata có cung cấp.

## Gate provenance cho canonical evidence

Functional gate và provenance gate được đánh giá riêng. Functional gate kiểm tra
coverage, independent validation, fairness và deterministic. Provenance gate yêu
cầu source commit, `git_dirty=false` và SHA-256 khớp cho `manifest.json`,
`results.csv`, `determinism_evidence.csv` và `pairwise_outcomes.csv`.

Functional `PASS` không tự động cho phép promotion. Thiếu artifact, checksum mismatch
hoặc source run dirty đều fail closed. Quy tắc objective/reference authoritative nằm
tại [ADR-0050](../decisions/ADR-0050-objective-va-benchmark-governance.md).

Level 2 V2 là canonical sau clean rerun ngày 2026-08-20: 84 bài, 756 lượt `VALID`,
252 nhóm deterministic và ba manifest `git_dirty=false`. Random là tầng quality
chính; stress và prefix là supporting evidence và không được trộn vào WIN/TIE/LOSS
random. V1 là `superseded`; quick UI chỉ là smoke protocol.

## Corpus nghiên cứu có định danh

`config/level_01/benchmarks/research_corpus.yaml` định nghĩa các case có tên thay vì chỉ dùng tích Descartes giữa số item và container. Mỗi case khai báo nhóm quy mô, độ khó, số item/container, kết quả kỳ vọng, thuật toán, config và mô tả. Một lần chạy ghi aggregate bất biến dưới `outputs/level_01/runs/<run_id>/`; từng source run vẫn là experiment được independent validator kiểm tra.

Quy tắc chọn reference:

1. objective nhỏ nhất trong nghiệm `OPTIMAL` hợp lệ là `proven_optimal`;
2. nếu không có optimal, objective nhỏ nhất trong nghiệm khả thi hợp lệ trên đúng
   `input_fingerprint` của run là `best_observed`;
3. exact `INFEASIBLE` tạo reference `proven_infeasible`;
4. trường hợp còn lại là `unavailable`.

Objective gap chỉ được báo khi có numeric reference. `best_observed` không phải
best-known của tài liệu học thuật và không được trình bày như global optimum.
Nhãn `best_known` trong artifact cũ vẫn đọc được nhưng phải hiển thị là legacy.
`INFEASIBLE_HEURISTIC` có thể khớp expected behavior của regression case, nhưng
chỉ exact MILP tạo chứng minh bất khả thi.

Artifact gồm `case_catalog.csv`, `results.csv`, `summary.csv`, `ranking.csv`, `references.csv` và `summary.json`. Manifest ghi checksum corpus/config, source runs, seed, environment, source commit và dependency versions.

Với thuật toán stochastic, `--seeds 7 11 19` chạy các trajectory độc lập.
`--repeats 2` chạy mỗi seed hai lần để đo nhiễu thời gian và kiểm tra khả năng tái
lập. Nếu bỏ `--seeds`, runner dùng `project.random_seed`. Seed trùng bị từ chối vì
việc lặp lại phải được khai báo qua `--repeats`.
