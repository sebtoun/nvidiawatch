import threading
import time

from concurrent.futures import ProcessPoolExecutor, Future
from typing import Optional, List, Tuple, Iterable
from stockscan.scanner import Scanner, ScanResult
from datetime import datetime


def update_scanner(scanner):
    return scanner.scan()


class StockMonitor:
    ScanTask = Future

    def __init__(self, scanners: List[Scanner], update_freq=30, max_thread=8):
        self._update_freq = update_freq
        self._scanners = scanners
        self._scan_tasks: Optional[List[Optional[StockMonitor.ScanTask]]] = None
        self._last_update_time = None
        self._update_requested = False

        # scan results
        now = datetime.now()
        self._last_results: List[ScanResult] = [ScanResult(now)] * len(scanners)
        self._last_stock_time: List[Optional[datetime]] = [None] * len(scanners)
        self._consecutive_errors: List[int] = [0] * len(scanners)

        # update thread
        self.pool = ProcessPoolExecutor(min(max_thread, len(scanners)))
        self._update_thread = None
        self.stop_update = False

    def _update_scanners(self):
        self._last_update_time = datetime.now()
        self._scan_tasks = [self.pool.submit(update_scanner, scanner) for scanner in self._scanners]
        self._update_requested = False

    def _update_loop(self):
        self._update_scanners()
        while not self.stop_update:
            # check pending updates
            update_pending = any(map(lambda f: f and f.done(), self._scan_tasks))
            if update_pending:
                for i, (previous, task) in enumerate(zip(self._last_results, self._scan_tasks)):
                    if task and task.done():
                        result: ScanResult = task.result()
                        if result.is_error:
                            self._consecutive_errors[i] += 1
                        else:
                            self._consecutive_errors[i] = 0
                        if result.is_in_stock:
                            self._last_stock_time[i] = result.timestamp
                        self._scan_tasks[i] = None
                        self._last_results[i] = result
            # trigger new update
            update_finished = not any(self._scan_tasks)
            delay_elapsed = (datetime.now() - self._last_update_time).total_seconds() >= self._update_freq
            if update_finished and (delay_elapsed or self._update_requested):
                self._update_scanners()
            else:
                time.sleep(0.5)

    def update_now(self) -> None:
        self._update_requested = True

    def start(self) -> None:
        assert self._update_thread is None, "Thread already running"
        self.stop_update = False
        self._update_thread = threading.Thread(target=self._update_loop)
        self._update_thread.start()

    def terminate(self) -> None:
        if self._update_thread is not None:
            self.stop_update = True
            self._update_thread.join()
        if self._scan_tasks is not None:
            for f in self._scan_tasks:
                if f and not f.done():
                    f.cancel()
        self.pool.shutdown(wait=True)

    @property
    def last_results(self) -> Iterable[Tuple[ScanResult, Optional[datetime], int]]:
        return zip(self._last_results, self._last_stock_time, self._consecutive_errors)

    @property
    def scanners(self) -> List[Scanner]:
        return self._scanners
