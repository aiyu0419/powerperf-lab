import csv
import json
import subprocess
import sys
from dataclasses import dataclass

import pytest

from powerperf import controller


@pytest.fixture
def fake_sampler(monkeypatch):
    instances = []

    class FakeSampler:
        def __init__(self, interval):
            self.interval = interval
            self.started = False
            self.stopped = False
            instances.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True
            return [
                {
                    "timestamp_utc": "2026-01-01T00:00:00+00:00",
                    "cpu_percent_system": 25.0,
                    "memory_available_bytes": 1_000_000,
                }
            ]

    monkeypatch.setattr(controller, "Sampler", FakeSampler)
    return instances


def test_parse_workload_output_accepts_json():
    payload = controller._parse_workload_output(
        json.dumps(
            {
                "workers": 2,
                "iterations": 1_000,
                "elapsed_s": 0.25,
                "checksum": 123,
            }
        )
    )

    assert payload == {
        "workers": 2,
        "iterations": 1_000,
        "elapsed_s": 0.25,
        "checksum": 123,
    }


def test_parse_workload_output_accepts_key_value_format():
    payload = controller._parse_workload_output(
        "workers=2 iterations=1000 elapsed_s=0.25 checksum=123"
    )

    assert payload == {
        "workers": 2,
        "iterations": 1_000,
        "elapsed_s": 0.25,
        "checksum": 123,
    }


@pytest.mark.parametrize(
    ("output", "message"),
    [
        ("", "no output"),
        ("ordinary log text", "neither JSON nor key=value"),
        ("[]", "must be an object"),
        ('{"workers": 2}', "integer checksum"),
        ('{"checksum": true}', "integer checksum"),
        ('{"checksum": 1, "elapsed_s": -1}', "non-negative number"),
        ('{"checksum": 1, "workers": "2"}', "workers must be an integer"),
        ('{"checksum": 1, "iterations": 1.3}', "workload iterations must be an integer"),
        ('{"checksum": 1, "elapsed_s": "0.25"}', "workload elapsed_s must be a non-negative number"),
        ('{"checksum": 1, "elapsed_s": -0.25}', "workload elapsed_s must be a non-negative number"),
    ],
)
def test_parse_workload_output_rejects_invalid_output(output, message):
    with pytest.raises(ValueError, match=message):
        controller._parse_workload_output(output)


def test_one_run_records_success(monkeypatch, tmp_path, fake_sampler):
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps(
            {
                "workers": 2,
                "iterations": 1_000,
                "elapsed_s": 0.25,
                "checksum": 123,
            }
        ),
        stderr="",
    )
    run_calls = []

    def fake_run(command, **kwargs):
        run_calls.append((command, kwargs))
        return completed

    monkeypatch.setattr(controller.subprocess, "run", fake_run)

    row = controller.one_run(
        workers=2,
        iterations=1_000,
        timeout=10,
        interval=0.5,
        block=3,
        warmup=False,
        out=tmp_path,
    )

    assert row["status"] == "ok"
    assert row["exit_code"] == 0
    assert row["workers"] == 2
    assert row["iterations"] == 1_000
    assert row["block"] == 3
    assert row["warmup"] is False
    assert row["workload_time_s"] == 0.25
    assert row["checksum"] == 123
    assert row["wall_time_s"] >= 0
    assert fake_sampler[0].interval == 0.5
    assert fake_sampler[0].started is True
    assert fake_sampler[0].stopped is True

    command, options = run_calls[0]
    assert command == [
        sys.executable,
        "-m",
        "powerperf.workload",
        "--workers",
        "2",
        "--iterations",
        "1000",
    ]
    assert options == {
        "capture_output": True,
        "text": True,
        "timeout": 10,
        "check": False,
    }

    with (tmp_path / "telemetry.csv").open(newline="", encoding="utf-8") as file:
        telemetry_rows = list(csv.DictReader(file))

    assert len(telemetry_rows) == 1
    assert telemetry_rows[0]["run_id"] == row["run_id"]
    assert telemetry_rows[0]["cpu_percent_system"] == "25.0"


def test_one_run_records_nonzero_exit(monkeypatch, tmp_path, fake_sampler):
    monkeypatch.setattr(
        controller.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=7,
            stdout="",
            stderr="worker failed",
        ),
    )

    row = controller.one_run(
        workers=1,
        iterations=100,
        timeout=10,
        interval=0.5,
        block=0,
        warmup=False,
        out=tmp_path,
    )

    assert row["status"] == "failed"
    assert row["exit_code"] == 7
    assert row["stderr"] == "worker failed"
    assert row["checksum"] is None


def test_one_run_records_timeout(monkeypatch, tmp_path, fake_sampler):
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd="powerperf.workload",
            timeout=2,
            stderr=b"partial error",
        )

    monkeypatch.setattr(controller.subprocess, "run", raise_timeout)

    row = controller.one_run(
        workers=1,
        iterations=100,
        timeout=2,
        interval=0.5,
        block=0,
        warmup=True,
        out=tmp_path,
    )

    assert row["status"] == "timeout"
    assert row["exit_code"] is None
    assert row["stderr"] == "timeout after 2s: partial error"
    assert fake_sampler[0].stopped is True


def test_one_run_rejects_mismatched_workload_output(
    monkeypatch,
    tmp_path,
    fake_sampler,
):
    monkeypatch.setattr(
        controller.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "workers": 4,
                    "iterations": 100,
                    "elapsed_s": 0.1,
                    "checksum": 10,
                }
            ),
            stderr="",
        ),
    )

    row = controller.one_run(
        workers=2,
        iterations=100,
        timeout=10,
        interval=0.5,
        block=0,
        warmup=False,
        out=tmp_path,
    )

    assert row["status"] == "invalid_output"
    assert "returned workers=4, expected 2" in row["stderr"]


@dataclass(frozen=True)
class ControllerConfigStub:
    worker_counts: tuple[int, ...] = (1, 2)
    iterations: int = 1_000
    repetitions: int = 2
    warmups: int = 1
    timeout_seconds: float = 30.0
    telemetry_interval_seconds: float = 0.5
    cooldown_seconds: float = 0.0
    random_seed: int = 42


def test_run_experiment_schedules_balanced_blocks(monkeypatch, tmp_path):
    config = ControllerConfigStub()
    run_calls = []
    sleep_calls = []

    monkeypatch.setattr(controller, "load_config", lambda path: config)
    monkeypatch.setattr(
        controller,
        "collect",
        lambda: {"platform": "test-platform"},
    )
    monkeypatch.setattr(
        controller.time,
        "sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    def fake_one_run(**kwargs):
        run_calls.append(kwargs)
        return {
            "run_id": f"run-{len(run_calls)}",
            "block": kwargs["block"],
            "workers": kwargs["workers"],
            "iterations": kwargs["iterations"],
            "warmup": kwargs["warmup"],
            "status": "ok",
            "exit_code": 0,
            "wall_time_s": 0.1,
            "workload_time_s": 0.09,
            "checksum": 123,
            "timestamp_utc": "2026-01-01T00:00:00+00:00",
            "stderr": "",
        }

    monkeypatch.setattr(controller, "one_run", fake_one_run)

    output = tmp_path / "results"
    controller.run_experiment(tmp_path / "config.json", output)

    assert len(run_calls) == 6
    assert len(sleep_calls) == 6
    assert all(seconds == 0.0 for seconds in sleep_calls)

    grouped_workers = {}
    for call in run_calls:
        key = (call["warmup"], call["block"])
        grouped_workers.setdefault(key, []).append(call["workers"])
        assert call["iterations"] == 1_000
        assert call["timeout"] == 30.0
        assert call["interval"] == 0.5

    assert set(grouped_workers) == {(True, 0), (False, 0), (False, 1)}
    assert all(sorted(workers) == [1, 2] for workers in grouped_workers.values())

    saved_config = json.loads((output / "config.json").read_text())
    saved_metadata = json.loads((output / "metadata.json").read_text())
    assert saved_config["worker_counts"] == [1, 2]
    assert saved_config["warmups"] == 1
    assert saved_metadata == {"platform": "test-platform"}

    with (output / "runs.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 6
    assert {row["status"] for row in rows} == {"ok"}


def test_run_experiment_rejects_existing_output_directory(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        controller,
        "load_config",
        lambda path: ControllerConfigStub(),
    )

    with pytest.raises(FileExistsError):
        controller.run_experiment(tmp_path / "config.json", tmp_path)