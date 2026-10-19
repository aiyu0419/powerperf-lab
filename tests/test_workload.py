import pytest

from powerperf.workload import compute, partitions, run


def test_partitions_cover_exact_work():
    for workers in (1, 2, 4, 8):
        parts = partitions(103, workers)

        assert parts[0][0] == 0
        assert parts[-1][1] == 103
        assert sum(end - start for start, end in parts) == 103
        assert all(start < end for start, end in parts)
        assert all(
            parts[index][1] == parts[index + 1][0]
            for index in range(len(parts) - 1)
        )


def test_compute_is_deterministic():
    assert compute(0, 100) == compute(0, 100)


def test_compute_chunks_are_additive():
    assert compute(0, 100) == compute(0, 40) + compute(40, 100)


def test_run():
    output = run(2_000, 2)

    assert output["iterations"] == 2_000
    assert output["workers"] == 2
    assert output["elapsed_s"] >= 0
    assert output["checksum"] == compute(0, 2_000)


@pytest.mark.parametrize(
    ("iterations", "workers"),
    [(0, 1), (-1, 1), (10, 0), (10, -1), (3, 4)],
)
def test_invalid_partitions(iterations, workers):
    with pytest.raises(ValueError):
        partitions(iterations, workers)