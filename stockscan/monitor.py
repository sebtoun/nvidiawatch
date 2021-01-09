import asyncio
import logging

from typing import Optional, List, Tuple, Iterable
from stockscan.scanner import Scanner, ScanResult
from datetime import datetime
from threading import Thread

logger = logging.getLogger(__name__)


async def update_scanner(scanner):
    return await scanner.scan()


class StockMonitor:
    def __init__(self, scanners: List[Scanner], update_freq=30, max_thread=8):
        self._update_freq = update_freq
        self._scanners = scanners
        self._last_update_time = None
        self._update_requested = False

        # scan results
        now = datetime.now()
        self._last_results: List[ScanResult] = [ScanResult(now)] * len(scanners)
        self._last_stock_time: List[Optional[datetime]] = [None] * len(scanners)
        self._consecutive_errors: List[int] = [0] * len(scanners)

        # update thread
        self.stop_update = False
        self._update_thread: Optional[Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._sleep_task: Optional[asyncio.Task] = None

    async def _update_scanners(self):
        logger.info("updating scanners")
        self._update_requested = False
        tasks = await asyncio.gather(*(scanner.scan() for scanner in self._scanners))
        logger.info("gathered %d results", len(tasks))
        for i, (previous, result) in enumerate(zip(self._last_results, tasks)):
            if result.is_error:
                self._consecutive_errors[i] += 1
            else:
                self._consecutive_errors[i] = 0
            if result.is_in_stock:
                self._last_stock_time[i] = result.timestamp
            self._last_results[i] = result

    async def update_loop(self):
        self.stop_update = False
        while not self.stop_update:
            # trigger new update
            self._last_update_time = datetime.now()
            await self._update_scanners()
            delay_elapsed = (datetime.now() - self._last_update_time).total_seconds()
            if delay_elapsed < self._update_freq and not self._update_requested:
                try:
                    self._sleep_task = asyncio.create_task(asyncio.sleep(self._update_freq - delay_elapsed))
                    await self._sleep_task
                except asyncio.CancelledError:
                    pass

    def interrupt_sleep(self) -> None:
        def cancel_sleep():
            if self._sleep_task:
                self._sleep_task.cancel()

        self._loop.call_soon_threadsafe(cancel_sleep)

    def update_now(self) -> None:
        self._update_requested = True
        self.interrupt_sleep()

    def _run_update_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.update_loop())

    def start(self) -> None:
        self._loop = asyncio.new_event_loop()
        # self._loop.set_debug(True)
        self._update_thread = Thread(target=self._run_update_loop, args=(self._loop,), daemon=True)
        self._update_thread.start()

    def terminate(self) -> None:
        self.stop_update = True
        self.interrupt_sleep()
        self._update_thread.join()

    @property
    def last_results(self) -> Iterable[Tuple[ScanResult, Optional[datetime], int]]:
        return zip(self._last_results, self._last_stock_time, self._consecutive_errors)

    @property
    def scanners(self) -> List[Scanner]:
        return self._scanners
