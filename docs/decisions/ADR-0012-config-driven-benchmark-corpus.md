# ADR-0012: Config-driven benchmark corpus

Status: accepted.

Algorithm count has grown enough that ad-hoc item/container matrices no longer provide a stable scientific comparison. We introduce a versioned YAML corpus with named cases, explicit scale and difficulty labels, expected outcomes, case-specific algorithms, and immutable aggregate artifacts.

The ordinary matrix benchmark remains supported. Both paths reuse the same experiment runner, independent validator, metric functions, output isolation, manifests, and seed semantics. The corpus adds reference classification and quality gaps without changing any Level 1 solver or constraint.

An exact `OPTIMAL` result is the only source of a proven-optimal objective. Larger cases use the explicitly weaker `best_known` label. Likewise, only exact `INFEASIBLE` proves infeasibility; heuristic failure retains its existing non-proof semantics.

The Streamlit dashboard reads persisted corpus CSVs through the application boundary. It does not contain benchmark computation and can later be replaced by another frontend.
