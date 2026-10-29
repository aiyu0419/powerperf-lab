# Power Performance

Python tools for evaluating CPU scaling with a fixed total amount of work across different worker counts. The experiment controller runs randomized, balanced blocks and saves run outcomes and system telemetry.

## Current status

The experiment controller and its unit tests are complete. The next phase is to analyze benchmark results and run additional experiment configurations.

Completed:

- Implemented the controller for randomized, balanced experiment blocks, workload execution, output validation, and result persistence.
- Completed controller unit tests covering parsing, run outcomes, telemetry, scheduling, and saved results.

Next steps:

- Analyze collected results, excluding warmups and accounting for failed or invalid runs.
- Compare execution time, speedup, variability, and system telemetry across worker counts.
- Run more configurations by varying worker counts, total iterations, repetitions, and cooldown settings.

Local checkout note: this mirror does not include `powerperf.config`, `powerperf.metadata`, `powerperf.telemetry`, `powerperf.workload`, `configs/cpu_scaling.json`, or `benchmark.py`. Running the commands below requires the complete project environment. No dependency manifest is included in this mirror.

## Files

| File | Purpose |
| --- | --- |
| `powerperf/controller.py` | Schedules experiments, launches workload processes, validates output, and records results. |
| `powerperf/__init__.py` | Package definition. |
| `test.py` | Standalone benchmark runner that verifies checksums and summarizes timing and speedup. |
| `tests/test_controller.py` | Pytest tests for parsing, outcomes, telemetry, and experiment scheduling. |

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

## Tests

In the complete project environment with pytest installed:

```sh
python3 -m pytest tests/test_controller.py
```

The tests use simulated workload processes and telemetry to check output validation, successful and failed runs, timeouts, mismatched parameters, balanced blocks, result persistence, and rejection of an existing output directory.
