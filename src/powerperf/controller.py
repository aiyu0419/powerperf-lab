"""Run balanced randomized benchmark blocks and persist every outcome."""

import argparse
import csv
import datetime as dt
import json
import random
import re
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import load_config, ConfigError
from .metadata import collect
from .telemetry import Sampler


FIELDS = [
    "run_id",
    "block",
    "workers",
    "iterations",
    "warmup",
    "status",
    "exit_code",
    "wall_time_s",
    "workload_time_s",
    "checksum",
    "timestamp_utc",
    "stderr",
]

TELEMETRY_FIELDS = [
    "run_id",
    "timestamp_utc",
    "cpu_percent_system",
    "memory_available_bytes",
]

OUTPUT_PATTERN = re.compile(
    r"\b(workers|iterations|elapsed_s|checksum)=([^\s]+)"
)


def _parse_workload_output(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise ValueError("workload produced no output")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        values = dict(OUTPUT_PATTERN.findall(text))
        if not values:
            raise ValueError("workload output is neither JSON nor key=value data")

        payload = {}
        for key in ("workers", "iterations", "checksum"):
            if key in values:
                try:
                    payload[key] = int(values[key])
                except ValueError as error:
                    raise ValueError(f"workload returned invalid {key}") from error

        if "elapsed_s" in values:
            try:
                payload["elapsed_s"] = float(values["elapsed_s"])
            except ValueError as error:
                raise ValueError("workload returned invalid elapsed_s") from error

    # Validate the parsed payload before returning it
    if not isinstance(payload, dict):
        raise ValueError("workload output must be an object")

    checksum = payload.get("checksum")
    if type(checksum) is not int:
        raise ValueError("workload output must contain an integer checksum")

    for key in ("workers", "iterations"):
        value = payload.get(key)
        if value is not None and type(value) is not int:
            raise ValueError(f"workload {key} must be an integer")

    elapsed = payload.get("elapsed_s")
    if elapsed is not None and (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or elapsed < 0
    ):
        raise ValueError("workload elapsed_s must be a non-negative number")

    return payload


def _append_telemetry(out: Path, run_id: str, samples: list[dict]) -> None:
    telemetry_path = out / "telemetry.csv"
    with telemetry_path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=TELEMETRY_FIELDS)
        # Write the header if the file is empty
        if file.tell() == 0:
            writer.writeheader()
        for sample in samples:
            writer.writerow({"run_id": run_id, **sample})

# Helper function to convert exception text to a string, when process is timed out
def _exception_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def one_run(
    workers: int,
    iterations: int,
    timeout: float,
    interval: float,
    block: int,
    warmup: bool,
    out: Path,
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    command = [
        sys.executable,
        "-m",
        "powerperf.workload",
        "--workers",
        str(workers),
        "--iterations",
        str(iterations),
    ]
    # Initialize the telemetry sampler before running the workload
    sampler = Sampler(interval)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    started = time.perf_counter()

    # Start the telemetry sampler before running the workload
    sampler.start()

    exit_code = None
    status = "error"
    stdout = ""
    stderr = ""

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        status = "ok" if exit_code == 0 else "failed"
    except subprocess.TimeoutExpired as error:
        status = "timeout"
        stdout = _exception_text(error.stdout)
        stderr = _exception_text(error.stderr)
        stderr = f"timeout after {timeout}s" + (
            f": {stderr}" if stderr else ""
        )
    except OSError as error:
        stderr = str(error)
    finally:
        wall_time = time.perf_counter() - started
        samples = sampler.stop()

    payload: dict[str, Any] = {}
    if status == "ok":
        try:
            payload = _parse_workload_output(stdout)

            returned_workers = payload.get("workers")
            if returned_workers is not None and returned_workers != workers:
                raise ValueError(
                    f"workload returned workers={returned_workers}, expected {workers}"
                )

            returned_iterations = payload.get("iterations")
            if returned_iterations is not None and returned_iterations != iterations:
                raise ValueError(
                    "workload returned "
                    f"iterations={returned_iterations}, expected {iterations}"
                )
        except (TypeError, ValueError) as error:
            status = "invalid_output"
            stderr = str(error)

    _append_telemetry(out, run_id, samples)

    return {
        "run_id": run_id,
        "block": block,
        "workers": workers,
        "iterations": iterations,
        "warmup": warmup,
        "status": status,
        "exit_code": exit_code,
        "wall_time_s": wall_time,
        "workload_time_s": payload.get("elapsed_s"),
        "checksum": payload.get("checksum"),
        "timestamp_utc": timestamp,
        "stderr": stderr[-2000:],
    }


def run_experiment(config_path: Path, out: Path) -> None:
    try:
        config = load_config(config_path)
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        raise

    out.mkdir(parents=True, exist_ok=False)
    (out / "config.json").write_text(
        json.dumps(asdict(config), indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "metadata.json").write_text(
        json.dumps(collect(), indent=2) + "\n",
        encoding="utf-8",
    )

    randomizer = random.Random(config.random_seed)
    runs_path = out / "runs.csv"

    with runs_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()

        phases = ((True, config.warmups), (False, config.repetitions))
        for warmup, blocks in phases:
            for block in range(blocks):
                worker_counts = list(config.worker_counts)
                randomizer.shuffle(worker_counts)

                for workers in worker_counts:
                    row = one_run(
                        workers=workers,
                        iterations=config.iterations,
                        timeout=config.timeout_seconds,
                        interval=config.telemetry_interval_seconds,
                        block=block,
                        warmup=warmup,
                        out=out,
                    )
                    writer.writerow(row)
                    file.flush()
                    print(
                        f"block={block} warmup={warmup} "
                        f"workers={workers} status={row['status']} "
                        f"wall={row['wall_time_s']:.3f}s",
                        flush=True,
                    )
                    time.sleep(config.cooldown_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/cpu_scaling.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            Path("results")
            / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        ),
    )
    args = parser.parse_args()

    try:
        run_experiment(args.config, args.output)
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    except FileExistsError:
        print(
            f"Output directory already exists: {args.output}",
            file=sys.stderr,
        )
        return 3
    except PermissionError as error:
        print(f"Permission error: {error}", file=sys.stderr)
        return 4
    except OSError as error:
        print(f"Experiment I/O error: {error}", file=sys.stderr)
        return 5
    except KeyboardInterrupt:
        print("Experiment interrupted by user", file=sys.stderr)
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
