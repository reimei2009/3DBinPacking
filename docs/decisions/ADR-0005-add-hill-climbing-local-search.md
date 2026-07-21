# ADR-0005: Add deterministic Hill Climbing after the greedy baseline

Status: accepted.

Hill Climbing reuses the Extreme-Point constructor as a repair operator and adds relocate, swap, reinsert, and container-elimination neighborhoods. This creates reusable local-search components before introducing Simulated Annealing, Tabu Search, or VNS.

Only strict lexicographic improvements are accepted. The method remains Level 1 fixed-orientation geometry/payload search and reports `FEASIBLE`, never `OPTIMAL`.
