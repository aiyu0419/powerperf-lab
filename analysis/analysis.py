"""Summarize controller results without third-party dependencies."""

import argparse
import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def summarize(path: Path, timing: str = "wall_time_s") -> tuple[list[dict], dict]:
    """Analyze one experiment, grouping measured successful runs by workers."""
    if timing not in {"wall_time_s", "workload_time_s"}:
        raise ValueError("unsupported timing field")
    groups = defaultdict(list)
    checksums = set()
    iterations_seen = set()
    counts = Counter()
    statuses = Counter()
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        required = {"workers", "iterations", "warmup", "status", "checksum", timing}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")
        for line, row in enumerate(reader, start=2):
            counts["total"] += 1
            warmup = row["warmup"].strip().lower()
            if warmup not in {"true", "false", "1", "0"}:
                raise ValueError(f"Row {line}: invalid warmup flag")
            if warmup in {"true", "1"}:
                counts["warmups"] += 1
                continue
            statuses[row["status"]] += 1
            if row["status"] != "ok":
                counts["unsuccessful"] += 1
                continue
            try:
                workers = int(row["workers"])
                iterations = int(row["iterations"])
                checksum = int(row["checksum"])
                if workers < 1 or iterations < 1:
                    raise ValueError("workers and iterations must be positive")
                iterations_seen.add(iterations)
                checksums.add(checksum)
                if not row[timing].strip():
                    counts["missing_timing"] += 1
                    continue
                elapsed = float(row[timing])
                if not math.isfinite(elapsed) or elapsed <= 0:
                    raise ValueError("timing must be finite and positive")
            except (ValueError, TypeError) as error:
                raise ValueError(f"Row {line}: {error}") from error
            groups[workers].append(elapsed)
            counts["included"] += 1
    if len(iterations_seen) > 1:
        raise ValueError("Mixed iteration counts: analyze each workload size separately")
    if len(checksums) > 1:
        raise ValueError("Checksum mismatch across successful measured runs")
    if not groups:
        raise ValueError("No successful measured runs with usable timing")

    baseline_workers = min(groups)
    baseline = statistics.median(groups[baseline_workers])
    summary = []
    for workers, values in sorted(groups.items()):
        median = statistics.median(values)
        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else None
        speedup = baseline / median
        summary.append({
            "workers": workers,
            "runs": len(values),
            "median_s": median,
            "mean_s": mean,
            "min_s": min(values),
            "max_s": max(values),
            "stdev_s": stdev,
            "cv_percent": 100 * stdev / mean if stdev is not None else None,
            "speedup": speedup,
            "relative_efficiency_percent": 100 * speedup * baseline_workers / workers,
        })
    return summary, {
        "counts": counts,
        "statuses": statuses,
        "baseline_workers": baseline_workers,
        "iterations": next(iter(iterations_seen)),
        "checksum": next(iter(checksums)),
        "timing": timing,
        "samples": dict(groups),
    }


def report_text(summary: list[dict], details: dict) -> str:
    counts = details["counts"]
    fastest = min(summary, key=lambda row: row["median_s"])
    lines = [
        "# CPU scaling analysis", "",
        f"Timing metric: `{details['timing']}`. Total iterations per run: {details['iterations']:,}.",
        f"Included {counts['included']} measured runs; excluded {counts['warmups']} warmups, "
        f"{counts['unsuccessful']} unsuccessful measured runs, and "
        f"{counts['missing_timing']} successful measured runs without the selected timing.",
        f"Checksum consistent across successful measured runs: `{details['checksum']}`.", "",
        "| Workers | Runs | Median (s) | Min (s) | Max (s) | CV (%) | Speedup | Relative efficiency (%) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in summary:
        cv = f"{row['cv_percent']:.2f}" if row["cv_percent"] is not None else "N/A"
        lines.append(
            f"| {row['workers']} | {row['runs']} | {row['median_s']:.6f} | "
            f"{row['min_s']:.6f} | {row['max_s']:.6f} | {cv} | "
            f"{row['speedup']:.2f}x | {row['relative_efficiency_percent']:.2f} |"
        )
    lines.extend([
        "", f"Speedup baseline: {details['baseline_workers']} worker(s). "
        "Relative efficiency is speedup divided by the worker-count increase from that baseline.",
        f"Lowest observed median: {fastest['workers']} worker(s), {fastest['median_s']:.6f} s.",
        "", "CV is sample standard deviation divided by mean timing. "
        "A single run cannot estimate variability. These descriptive results do not establish statistical significance.",
        "Analyze each experiment separately: workload size, machine, and measurement conditions must be comparable.",
        "CPU and memory telemetry are not power or energy measurements.",
    ])
    if details["statuses"]:
        lines.extend(["", "Measured run statuses: " + ", ".join(
            f"{status}={count}" for status, count in sorted(details["statuses"].items())
        ) + "."])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="experiment directory or runs.csv")
    parser.add_argument("--timing", choices=["wall_time_s", "workload_time_s"], default="wall_time_s")
    parser.add_argument("--output", type=Path, required=True, help="new directory for the analysis")
    parser.add_argument("--plots", action="store_true", help="also save PNG and PDF charts (requires matplotlib)")
    args = parser.parse_args()
    source = args.results / "runs.csv" if args.results.is_dir() else args.results
    try:
        summary, details = summarize(source, args.timing)
        if args.plots:
            from .visualization import load_plotting
            load_plotting()
        args.output.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError, ImportError) as error:
        parser.exit(1, f"Analysis failed: {error}\n")
    with (args.output / "summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    report = report_text(summary, details)
    if args.plots:
        from .visualization import plot_results
        plot_results(summary, details, args.output)
        report += "\n## Charts\n\n![CPU scaling charts](scaling.png)\n\n[Download PDF](scaling.pdf)\n"
    (args.output / "report.md").write_text(f"Source: {source.resolve()}\n\n" + report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
