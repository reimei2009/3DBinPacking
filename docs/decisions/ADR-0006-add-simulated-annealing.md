# ADR-0006: Add seeded Simulated Annealing

Status: accepted, 2026-07-21.

Level 1 needs a local metaheuristic that can escape local optima without introducing future-level physics. We add seeded Simulated Annealing over the same complete Extreme-Point destroy-and-repair solutions used by Hill Climbing.

Neighborhood construction is extracted into one shared canonical module. Hill Climbing keeps strict improvement; Simulated Annealing may accept a worse current state through the Metropolis rule but always returns the best lexicographic state observed. The project seed controls all randomness. Independent Level 1 validation remains mandatory.

This decision adds no rotation, support, stacking, stability, or other Level 2 constraint.
