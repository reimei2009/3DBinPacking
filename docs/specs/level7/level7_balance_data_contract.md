# Level 7 data contract — container center of mass and balance

Status: **experimental generic runtime with frozen CLI regression fixtures**.

Level 7 inherits Level 6 constraints and uses canonical item `weight_kg`,
placement dimensions, and coordinates to calculate a center of mass for every
used container. It does not alter the contracts, defaults, validators, or
outputs of Levels 1–6.

For container \(k\), with item geometric centers
\((x_i+l_i/2, y_i+w_i/2, z_i+h_i/2)\):

\[
X_k^{cg}=\frac{\sum_{i\in k}w_i(x_i+l_i/2)}{\sum_{i\in k}w_i},\qquad
Y_k^{cg}=\frac{\sum_{i\in k}w_i(y_i+w_i/2)}{\sum_{i\in k}w_i}.
\]

The normalized horizontal band is:

\[
|X_k^{cg}/L_k-t_k^x|\le\tau_k^x,\qquad
|Y_k^{cg}/W_k-t_k^y|\le\tau_k^y.
\]

`config/level_07/balance_rules.yaml` defines synthetic profile
`symmetric_center_band_v1`, target `(0.5, 0.5)`, and tolerance `0.15` on each
horizontal axis. These are research parameters only; they are not inferred from
payload, stackability, or material strength.

The generic Best Fit and FFD runtimes accept configured input counts and item
selection. They create normal isolated runs under `outputs/level_07/runs/` and
write `solution/center_of_mass.csv`, `validation/balance_validation.json`, and
all inherited Level 6 artifacts. Final validation is mandatory. The frozen
four-item and discriminator fixtures remain CLI-only regression evidence.

Inactive: axle limits, floor-zone load limits, door clearance, dynamic transport
loads, rollover stability, moments, suspension, and vehicle certification.
