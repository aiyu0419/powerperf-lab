# Power Performance

Python tools for evaluating CPU scaling with a fixed total amount of work across different worker counts. The experiment controller runs randomized, balanced blocks and saves run outcomes and system telemetry.

## Current status

The fixed-total-work CPU experiment pipeline is complete through result analysis and visualization. The next phase is to expand the framework horizontally with memory-intensive and I/O-intensive workloads while preserving the same experiment controls and result format.

Completed:

- Implemented the CPU-bound multiprocessing workload with fixed total work across worker counts.
- Implemented the controller for randomized balanced blocks, warmups, repetitions, workload execution, output validation, telemetry, and result persistence.
- Added statistical analysis for filtering measured runs, timing summaries, speedup, parallel efficiency, variability, and checksum consistency.
- Added visualization for execution time, speedup, efficiency, and timing distributions.
- Added unit tests for workload partitioning, configuration validation, and controller behavior.

Next steps:

- Define a shared workload interface and add workload selection to experiment configuration.
- Add a fixed-total-work memory-intensive workload for studying memory-bandwidth scaling.
- Add a fixed-total-work I/O-intensive workload with controlled file size, block size, and read/write mode.
- Extend result fields, analysis, visualization, and tests to support CPU, memory, and I/O workloads without mixing incomparable experiments.
- Document workload-specific methodology, operating-system cache effects, and reproducibility requirements.

## Files

| File | Purpose |
| --- | --- |
| `powerperf/controller.py` | Schedules experiments, launches workload processes, validates output, and records results. |
| `powerperf/__init__.py` | Package definition. |
| `test.py` | Standalone benchmark runner that verifies checksums and summarizes timing and speedup. |
| `tests/test_controller.py` | Pytest tests for parsing, outcomes, telemetry, and experiment scheduling. |
| `analysis/analysis.py` | Analyzes controller results and writes a summary CSV and Markdown report. |
| `analysis/visualization.py` | Creates scaling and timing-distribution plots from analyzed results. |

## Requirements

- Python 3.10 or newer, based on the syntax used in the supplied code.
- `pytest` to run the controller tests.
- The workload, support modules, and configuration from the complete project environment.

## Standalone benchmark runner

Supply a Python benchmark that accepts `--workers` and `--iterations` and prints `checksum=<nonnegative integer>`. Its checksum must remain consistent across runs and worker counts for the same total iterations.

```sh
python3 test.py --benchmark /path/to/benchmark.py --workers 1 2 4 8 --iterations 40000000 --repetitions 5 --seed 0
```

The runner checks the benchmark's syntax, shuffles all scheduled runs with the supplied seed, executes them sequentially, and verifies their checksums. It reports median, minimum, and maximum whole-program wall time, plus speedup relative to the smallest worker count tested. Timing includes process startup and shutdown.

## Experiment controller

In the complete project environment, run from the project root:

```sh
python3 -m powerperf.controller --config configs/cpu_scaling.json --output results/cpu-scaling
```

The output directory must not already exist. If omitted, the output path defaults to `results/YYYYMMDD-HHMMSS` using local time.

The controller expects the loaded configuration to expose these fields; parsing rules and defaults are defined by the configuration module:

| Field | Purpose |
| --- | --- |
| `worker_counts` | Worker counts included once in each block. |
| `iterations` | Total iterations requested for each run. |
| `warmups` | Number of warmup blocks. |
| `repetitions` | Number of measured blocks. |
| `random_seed` | Seed for randomizing worker order within each block. |
| `timeout_seconds` | Workload subprocess timeout. |
| `telemetry_interval_seconds` | Sampling interval passed to the telemetry sampler. |
| `cooldown_seconds` | Pause after each run, including warmups. |

Warmup blocks run first. Within each block, every configured worker count runs once in shuffled order. Warmup and measured block numbers each start at zero. Warmup outcomes remain in the results and should be excluded from measured summaries.

### Workload output

The controller runs `python -m powerperf.workload --workers N --iterations M`. A successful workload must emit either a JSON object or recognized `key=value` data:

```json
{"workers": 2, "iterations": 1000, "elapsed_s": 0.25, "checksum": 123}
```

```text
workers=2 iterations=1000 elapsed_s=0.25 checksum=123
```

`checksum` is required and must be an integer. Optional `workers` and `iterations` must be integers matching the request. Optional `elapsed_s` must be a nonnegative number. The controller records checksums but does not compare them across runs; the standalone runner does.

### Saved results

| Output | Contents |
| --- | --- |
| `config.json` | Serialized experiment configuration. |
| `metadata.json` | Data returned by the metadata collector. |
| `runs.csv` | Run ID, block, worker count, iterations, warmup flag, status, exit code, timings, checksum, UTC timestamp, and stderr. |
| `telemetry.csv` | Samples linked by run ID, including UTC timestamp, system CPU percentage, and available memory in bytes. |

Run statuses are `ok`, `failed` (nonzero exit), `timeout`, `error` (process launch failure), and `invalid_output`. Each completed controller iteration writes and flushes its outcome. Stored stderr is limited to its final 2,000 characters.

`wall_time_s` measures the controller's elapsed time around sampling startup and workload execution; `workload_time_s` comes from the workload's optional `elapsed_s` output. These measurements have different scopes. The supplied code does not record power or energy measurements.

## Data analysis

For analysis and visualization together, install the plotting dependency and run:

```sh
python3 -m pip install -r requirements-analysis.txt
python3 -m powerperf.analysis results/cpu-scaling --output analysis/cpu-scaling --plots
```

This produces `summary.csv`, `report.md`, `scaling.png`, and `scaling.pdf`. The charts show median execution time with minimum-to-maximum whiskers, observed versus ideal speedup, relative parallel efficiency, and timing distributions with individual samples. Whiskers show the observed range, not confidence intervals. Each panel uses the same filtered data as the summary. The report embeds the chart and links to the PDF. Matplotlib is only required with `--plots`.

Analyze one experiment directory (or supply its `runs.csv` directly):

```sh
python3 -m analysis.analysis results/cpu-scaling --output analysis/cpu-scaling
```

This command uses only the Python standard library and does not require the controller's support modules. The analysis output directory must be new. It creates `summary.csv` and `report.md`; the original results are unchanged.

Warmups and unsuccessful measured runs are excluded. Successful runs without the selected timing are counted and excluded. Mixed iteration counts, inconsistent checksums among successful measured runs, and nonpositive or nonfinite timings cause analysis to stop.

The summary includes sample count, median, mean, minimum, maximum, sample standard deviation, coefficient of variation, speedup, and relative efficiency for each worker count. Speedup uses the smallest included worker count as the baseline. Relative efficiency accounts for the increase in worker count from that baseline. Variability is unavailable for a single sample.

By default, analysis uses controller wall time. To analyze workload-reported timing instead:

```sh
python3 -m powerperf.analysis results/cpu-scaling --timing workload_time_s --output analysis/cpu-scaling-workload
```

Analyze experiments separately to keep workload size and machine conditions comparable. Review exclusions and sample counts before drawing conclusions. Telemetry correlation and power or energy analysis are not implemented by this command. No collected result files are included in this checkout yet.

## Tests

In the complete project environment with pytest installed:

```sh
python3 -m pytest tests/test_controller.py
```
```sh
python3 tests/performance/benchmark_scaling.py --benchmark powerperf/workload.py --workers 1 2 4 8 --iterations 40000000 --repetitions 5 --seed 0
```
The tests use simulated workload processes and telemetry to check output validation, successful and failed runs, timeouts, mismatched parameters, balanced blocks, result persistence, and rejection of an existing output directory.
