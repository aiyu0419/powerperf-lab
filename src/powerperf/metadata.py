import datetime as dt
import platform
import sys
import psutil

def collect():
    return {"captured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "platform": platform.platform(), "machine": platform.machine(),
            "processor": platform.processor(), "python": sys.version,
            "logical_cpus": psutil.cpu_count(logical=True),
            "physical_cpus_reported": psutil.cpu_count(logical=False),
            "memory_bytes": psutil.virtual_memory().total,
            "note": "CPU frequency, power and temperature not measured."}