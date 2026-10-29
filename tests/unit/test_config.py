import json

import pytest

from powerperf.config import ConfigError, ControllerConfig, load_config, validate_config


def valid_config():
    return {
        "worker_counts": [1, 2, 4, 8],
        "iterations": 8_000_000,
        "repetitions": 20,
        "warmups": 1,
        "timeout_seconds": 180,
        "telemetry_interval_seconds": 0.5,
        "cooldown_seconds": 2.0,
        "random_seed": 42,
    }


def test_accepts_valid_config():
    config = validate_config(valid_config())

    assert config == ControllerConfig(
        worker_counts=[1, 2, 4, 8],
        iterations=8_000_000,
        repetitions=20,
        warmups=1,
        timeout_seconds=180.0,
        telemetry_interval_seconds=0.5,
        cooldown_seconds=2.0,
        random_seed=42,
    )


@pytest.mark.parametrize("missing_key", valid_config().keys())
def test_rejects_each_missing_key(missing_key):
    raw = valid_config()
    del raw[missing_key]

    with pytest.raises(ValueError, match="Missing configuration keys"):
        validate_config(raw)


def test_rejects_unknown_key():
    raw = valid_config()
    raw["worker_count"] = 4  # Likely typo.

    with pytest.raises(ValueError, match="Unknown configuration keys"):
        validate_config(raw)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("worker_counts", None, "non-empty list"),
        ("worker_counts", [], "non-empty list"),
        ("worker_counts", [1, 0], "positive integers"),
        ("worker_counts", [1, -2], "positive integers"),
        ("worker_counts", [1, 2.5], "positive integers"),
        ("worker_counts", [1, True], "positive integers"),
        ("worker_counts", [1, 2, 2], "duplicates"),
        ("iterations", 0, "positive integer"),
        ("iterations", -1, "positive integer"),
        ("iterations", 1.5, "positive integer"),
        ("iterations", True, "positive integer"),
        ("repetitions", 0, "positive integer"),
        ("repetitions", -1, "positive integer"),
        ("repetitions", 1.5, "positive integer"),
        ("repetitions", True, "positive integer"),
        ("warmups", -1, "non-negative integer"),
        ("warmups", 1.5, "non-negative integer"),
        ("warmups", True, "non-negative integer"),
        ("timeout_seconds", 0, "positive"),
        ("timeout_seconds", -1, "positive"),
        ("timeout_seconds", "180", "positive"),
        ("timeout_seconds", True, "positive"),
        ("telemetry_interval_seconds", 0, "positive"),
        ("telemetry_interval_seconds", -0.5, "positive"),
        ("telemetry_interval_seconds", "0.5", "positive"),
        ("telemetry_interval_seconds", True, "positive"),
        ("cooldown_seconds", -1, "non-negative"),
        ("cooldown_seconds", "2.0", "non-negative"),
        ("cooldown_seconds", True, "non-negative"),
        ("random_seed", 1.5, "integer"),
        ("random_seed", "42", "integer"),
        ("random_seed", True, "integer"),
    ],
)
def test_rejects_invalid_field_values(key, value, message):
    raw = valid_config()
    raw[key] = value

    with pytest.raises(ValueError, match=message):
        validate_config(raw)

# Test relationships between fields separately:
def test_rejects_worker_count_greater_than_iterations():
    raw = valid_config()
    raw["worker_counts"] = [1, 4]
    raw["iterations"] = 3

    with pytest.raises(ValueError, match="cannot exceed iterations"):
        validate_config(raw)


@pytest.mark.parametrize("interval", [180, 181])
def test_rejects_telemetry_interval_not_less_than_timeout(interval):
    raw = valid_config()
    raw["timeout_seconds"] = 180
    raw["telemetry_interval_seconds"] = interval

    with pytest.raises(ValueError, match="less than timeout"):
        validate_config(raw)


def test_accepts_zero_warmups_and_cooldown():
    raw = valid_config()
    raw["warmups"] = 0
    raw["cooldown_seconds"] = 0

    config = validate_config(raw)

    assert config.warmups == 0
    assert config.cooldown_seconds == 0.0

#Then test file loading independently using pytest’s temporary directory:
def test_load_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(valid_config()))

    config = load_config(path)

    assert config.worker_counts == [1, 2, 4, 8]


def test_load_config_rejects_missing_file(tmp_path):
    path = tmp_path / "missing.json"

    with pytest.raises(ConfigError, match="not found"):
        load_config(path)


def test_load_config_rejects_invalid_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"worker_counts": [1, 2}')

    with pytest.raises(ConfigError, match="Invalid JSON"):
        load_config(path)


@pytest.mark.parametrize("content", ["[]", '"text"', "42", "null"])
def test_load_config_rejects_non_object_root(tmp_path, content):
    path = tmp_path / "config.json"
    path.write_text(content)

    with pytest.raises(ConfigError, match="must be a JSON object"):
        load_config(path)


def test_load_config_rejects_invalid_configuration(tmp_path):
    raw = valid_config()
    raw["repetitions"] = 0

    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw))

    with pytest.raises(ConfigError, match="repetitions"):
        load_config(path)