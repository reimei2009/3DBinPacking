# ADR-0024: Require explicit delivery metadata and start with straight-path LIFO evidence

Status: Accepted.

Level 8 must not infer delivery priority from raw 3DBPPsi fields or item order.
An active Level 8 item needs explicit priority, stop ID, and provenance through
the shared CSV/YAML source adapter.

The first unloadability model uses a static, axis-aligned straight path to a
configured container face. It reports direct blockers and counts only later
delivery blockers as direct rehandles. This makes LIFO evidence independently
testable while avoiding unsupported claims about equipment, temporary storage,
or a complete physical removal schedule.

An exact sequence model may replace this as a future Level 8 extension, but it
must preserve the same explicit data provenance and independent validation
boundary.
