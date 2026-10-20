from dataclasses import dataclass
from typing import Any
import os
import json
from pathlib import Path


@dataclass(frozen=True)
class ControllerConfig:
    worker_counts: list[int]
    iterations: int
    repetitions: int
    warmups: int
    timeout_seconds: float
    telemetry_interval_seconds: float
    cooldown_seconds: float
    random_seed: int


REQUIRED_KEYS = {
    "worker_counts",
    "iterations",
    "repetitions",
    "warmups",
    "timeout_seconds",
    "telemetry_interval_seconds",
    "cooldown_seconds",
    "random_seed",
}


def is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def validate_config(raw: dict[str, Any]) -> ControllerConfig:
    missing = REQUIRED_KEYS - raw.keys()
    unknown = raw.keys() - REQUIRED_KEYS

    if missing:
        raise ValueError(f"Missing configuration keys: {sorted(missing)}")

    if unknown:
        raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")

    worker_counts = raw["worker_counts"]

    if not isinstance(worker_counts, list) or not worker_counts:
        raise ValueError("worker_counts must be a non-empty list")

    if not all(is_integer(value) and value > 0 for value in worker_counts):
        raise ValueError("worker_counts must contain positive integers")

    if len(worker_counts) != len(set(worker_counts)):
        raise ValueError("worker_counts must not contain duplicates")

    if not is_integer(raw["iterations"]) or raw["iterations"] < 1:
        raise ValueError("iterations must be a positive integer")

    if max(worker_counts) > raw["iterations"]:
        raise ValueError("worker count cannot exceed iterations")

    if not is_integer(raw["repetitions"]) or raw["repetitions"] < 1:
        raise ValueError("repetitions must be a positive integer")

    if not is_integer(raw["warmups"]) or raw["warmups"] < 0:
        raise ValueError("warmups must be a non-negative integer")

    if (
        not is_number(raw["timeout_seconds"])
        or raw["timeout_seconds"] <= 0
    ):
        raise ValueError("timeout_seconds must be positive")

    if (
        not is_number(raw["telemetry_interval_seconds"])
        or raw["telemetry_interval_seconds"] <= 0
    ):
        raise ValueError("telemetry_interval_seconds must be positive")

    if raw["telemetry_interval_seconds"] >= raw["timeout_seconds"]:
        raise ValueError(
            "telemetry_interval_seconds must be less than timeout_seconds"
        )

    if (
        not is_number(raw["cooldown_seconds"])
        or raw["cooldown_seconds"] < 0
    ):
        raise ValueError("cooldown_seconds must be non-negative")

    if not is_integer(raw["random_seed"]):
        raise ValueError("random_seed must be an integer")

    available_cpus = os.cpu_count()
    if available_cpus and max(worker_counts) > available_cpus:
        print(
            f"Warning: {max(worker_counts)} workers requested, "
            f"but only {available_cpus} logical CPUs detected"
        )

    return ControllerConfig(
        worker_counts=worker_counts,
        iterations=raw["iterations"],
        repetitions=raw["repetitions"],
        warmups=raw["warmups"],
        timeout_seconds=float(raw["timeout_seconds"]),
        telemetry_interval_seconds=float(
            raw["telemetry_interval_seconds"]
        ),
        cooldown_seconds=float(raw["cooldown_seconds"]),
        random_seed=raw["random_seed"],
    )

    """load configuration from a JSON file."""
def load_config(path: Path) -> ControllerConfig:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        raise ConfigError(f"Configuration file not found: {path}")
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"Invalid JSON at line {error.lineno}, "
            f"column {error.colno}: {error.msg}"
        )

    if not isinstance(raw, dict):
        raise ConfigError("Configuration root must be a JSON object")

    try:
        return validate_config(raw)
    except ValueError as error:
        raise ConfigError(f"Invalid configuration: {error}")
        
    #for controller configuration errors
class ConfigError(Exception):
    pass