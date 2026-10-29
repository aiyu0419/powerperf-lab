"""Low-rate system telemetry. Process-tree CPU time is captured separately."""
import datetime as dt
import threading
import time
import psutil

class Sampler:
    def __init__(self, interval: float = 0.5):
        if interval <= 0:
            raise ValueError("interval must be positive")
        self.interval = interval
        self.samples = []
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        psutil.cpu_percent(interval=None)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.wait(self.interval):
            mem = psutil.virtual_memory()
            self.samples.append({"timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                                 "cpu_percent_system": psutil.cpu_percent(interval=None),
                                 "memory_available_bytes": mem.available})

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        return list(self.samples)