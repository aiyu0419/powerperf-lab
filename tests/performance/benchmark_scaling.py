"""Run and validate the fixed-total-work multiprocessing benchmark."""

import argparse
import random
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path


CHECKSUM_PATTERN = re.compile(r"checksum=(\d+)")


def run_benchmark(
    benchmark: Path,
    workers: int,
    iterations: int,
) -> tuple[float, int, str]:
    command = [
        sys.executable,
        str(benchmark),
        "--workers",
        str(workers),
        "--iterations",
        str(iterations),
    ]

    started = time.perf_counter()
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - started

    match = CHECKSUM_PATTERN.search(completed.stdout)
    if match is None:
        raise RuntimeError(
            f"Could not find 'checksum=<number>' in output:\n{completed.stdout}"
        )

    return elapsed, int(match.group(1)), completed.stdout.strip()


def check_syntax(benchmark: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(benchmark)],
        check=True,
        capture_output=True,
        text=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and measure a multiprocessing benchmark."
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("benchmark.py"),
        help="benchmark program to execute (default: benchmark.py)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        nargs="+",
        default=[1, 2, 4, 8],
        help="worker counts to test (default: 1 2 4 8)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=40_000_000,
        help="fixed total iterations per run (default: 40000000)",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=5,
        help="runs per worker count (default: 5)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="randomization seed for run order (default: 0)",
    )
    args = parser.parse_args()

    if args.iterations < 1:
        parser.error("--iterations must be positive")
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    if any(workers < 1 for workers in args.workers):
        parser.error("all --workers values must be positive")
    if len(set(args.workers)) != len(args.workers):
        parser.error("--workers values must be unique")

    return args


def main() -> None:
    args = parse_args()
    benchmark = args.benchmark.resolve()

    if not benchmark.is_file():
        raise SystemExit(f"Benchmark file not found: {benchmark}")

    print(f"Checking syntax: {benchmark}")
    try:
        check_syntax(benchmark)
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or "syntax check failed"
        raise SystemExit(message) from error

    schedule = [
        workers
        for _ in range(args.repetitions)
        for workers in args.workers
    ]
    random.Random(args.seed).shuffle(schedule)

    timings: dict[int, list[float]] = {
        workers: [] for workers in args.workers
    }
    expected_checksum: int | None = None

    print(
        f"Running {len(schedule)} tests sequentially "
        f"({args.iterations:,} iterations each)"
    )

    for run_number, workers in enumerate(schedule, start=1):
        try:
            elapsed, checksum, output = run_benchmark(
                benchmark,
                workers,
                args.iterations,
            )
        except subprocess.CalledProcessError as error:
            details = error.stderr.strip() or error.stdout.strip()
            raise SystemExit(
                f"Benchmark failed with {workers} workers:\n{details}"
            ) from error

        if expected_checksum is None:
            expected_checksum = checksum
        elif checksum != expected_checksum:
            raise SystemExit(
                f"Checksum mismatch with {workers} workers: "
                f"expected {expected_checksum}, received {checksum}"
            )

        timings[workers].append(elapsed)
        print(
            f"[{run_number:>2}/{len(schedule)}] "
            f"workers={workers:<3} elapsed={elapsed:.6f}s  {output}"
        )

    medians = {
        workers: statistics.median(values)
        for workers, values in timings.items()
    }
    baseline_workers = min(args.workers)
    baseline = medians[baseline_workers]

    print(f"\nChecksum verified: {expected_checksum}")
    print("\nSummary (whole-program wall time)")
    print("workers  median_s   min_s      max_s      speedup")
    for workers in sorted(args.workers):
        values = timings[workers]
        speedup = baseline / medians[workers]
        print(
            f"{workers:>7}  {medians[workers]:>8.6f}  "
            f"{min(values):>8.6f}  {max(values):>8.6f}  {speedup:>7.2f}x"
        )

    print(f"\nSpeedup baseline: {baseline_workers} worker(s)")


if __name__ == "__main__":
    main()
