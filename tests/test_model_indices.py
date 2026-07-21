from container_packing.models.level_01.constants import DIRECTIONS
from container_packing.models.level_01.model_indices import ModelIndices


def test_reference_index_counts_and_contiguity():
    indices = ModelIndices(20, 5)
    assert indices.n_pairs == 190
    assert indices.n_variables == 5865
    values = {indices.u(k) for k in range(5)}
    values |= {indices.a(i, k) for i in range(20) for k in range(5)}
    values |= {f(i) for f in (indices.x, indices.y, indices.z) for i in range(20)}
    values |= {indices.delta(i, j, k, d) for i in range(20) for j in range(i + 1, 20) for k in range(5) for d in DIRECTIONS}
    assert values == set(range(5865))


def test_pair_number_is_contiguous():
    indices = ModelIndices(20, 5)
    assert [indices.pair_number(i, j) for i in range(20) for j in range(i + 1, 20)] == list(range(190))
