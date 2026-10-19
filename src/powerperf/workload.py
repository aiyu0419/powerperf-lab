"""Fixed-total-work, CPU-bound, multi-process benchmark."""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor

MASK = (1 << 64) - 1
def compute(start: int, end: int) -> int:
    total = 0
    for x in range(start, end):
        total += (x * x + 3 * x + 7) % 1000003
    return total

# Partition the total number of iterations into ranges for each worker
# example: partition(10, 3) -> [(0, 4), (4, 7), (7, 10)]
def partitions(iterations: int, workers: int) -> list[tuple[int, int]]:
    if iterations <= 0 or workers <= 0 or workers > iterations:
        raise ValueError("require iterations >= workers >= 1")
    if workers > iterations:
        raise ValueError("workers cannot exceed iterations")
    base, remainder = divmod(iterations, workers)
    ranges = []
    start = 0

    for i in range(workers):
        count = base + (1 if i < remainder else 0)
        end = start + count
        ranges.append((start, end))
        start = end
    return ranges

# Helper function to run a single chunk of work in a separate process
def _run_chunk(chunk: tuple[int, int]) -> int:
    return compute(*chunk)

def run(total: int, workers: int) -> dict:
    chunks = partitions(total, workers)
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        checksums = list(pool.map(_run_chunk, chunks))
    elapsed = time.perf_counter() - start
    return {"workers": workers, "iterations": total, "elapsed_s": elapsed,
            "checksum": sum(checksums) & MASK}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, required=True)
    parser.add_argument('--iterations', type=int, default=4_000_000)
    args = parser.parse_args()
    print(json.dumps(run(args.iterations, args.workers)), flush=True)
    


if __name__ == '__main__':
    main()