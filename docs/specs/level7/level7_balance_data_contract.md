# Level 7 data contract — container center of mass and balance

Status: **registered CLI-only acceptance fixture; no practical solver and no
Streamlit exposure**.

Level 7 inherits the Level 6 fixture constraints and uses canonical item
`weight_kg`, placement dimensions, and coordinates to calculate a per-container
center of mass. It does not alter Levels 1–6, their objectives, defaults,
validators, or outputs.

For each used container \(k\), with item geometric centers
\((x_i+l_i/2, y_i+w_i/2, z_i+h_i/2)\):

\[
X_k^{cg}=\frac{\sum_{i\in k} w_i(x_i+l_i/2)}{\sum_{i\in k}w_i},\qquad
Y_k^{cg}=\frac{\sum_{i\in k} w_i(y_i+w_i/2)}{\sum_{i\in k}w_i}.
\]

The initial profile constrains normalized horizontal offsets:

\[
|X_k^{cg}/L_k-t^x_k|\le\tau^x_k,\qquad
|Y_k^{cg}/W_k-t^y_k|\le\tau^y_k.
\]

`config/level_07/balance_rules.yaml` defines synthetic profile
`symmetric_center_band_v1`, target `(0.5, 0.5)`, and tolerance `0.15` on each
horizontal axis. These values are research provenance only; they are not vehicle
certification and are never inferred from payload, stackability, or strength.

The controlled runtime accepts only the versioned prefix 4-item / 1-container /
local / fixed-XYZ fixture. It loads canonical fixture placements and explicit
nesting relations, then independently composes the Level 6 bundle with balance
validation. It returns `VALIDATION_ONLY` and no objective. CLI `list`,
`prepare`, `run`, and `validate` can access it; Streamlit cannot.

Every run writes only under `outputs/level_07/runs/<run_id>/`, including
`solution/center_of_mass.csv`, `validation/balance_validation.json`, and all
inherited compound, support, stackability, and load-transfer artifacts.

Inactive: a practical balance-aware solver, floor-zone load limits, door
clearance, axle limits, dynamic transport loads, rollover stability, moment,
suspension, and vehicle certification.
