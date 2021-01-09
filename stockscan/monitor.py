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

        # scan results
        now = datetime.now()
        self._last_results: List[ScanResult] = [ScanResult(now)] * len(scanners)
        self._last_stock_time: List[Optional[datetime]] = [None] * len(scanners)
        self._consecutive_errors: List[int] = [0] * len(scanners)

        # update thread
        self.stop_update = False
        self._update_thread: Optional[Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # cancel events
        self._cancel_event = None

    async def _update_scanners(self):
        async def result_with_index(i):
            res = await self._scanners[i].scan()
            return i, res

        for task in asyncio.as_completed([result_with_index(i) for i in range(len(self._scanners))]):
            i, result = await task
            if result.is_error:
                self._consecutive_errors[i] += 1
            else:
                self._consecutive_errors[i] = 0
            if result.is_in_stock:
                self._last_stock_time[i] = result.timestamp
            self._last_results[i] = result

    async def cancelable(self, coro):
        done, pending = await asyncio.wait([coro, self._cancel_event.wait()], return_when=asyncio.FIRST_COMPLETED)
        if self._cancel_event.is_set():
            for task in pending:
                if not task.cancelled():
                    task.cancel()
                return await task
        return next(iter(done)).result()

    async def update_round(self):
        # trigger new update
        self._last_update_time = datetime.now()
        await self._update_scanners()
        # wait remaining time
        delay_elapsed = (datetime.now() - self._last_update_time).total_seconds()
        if delay_elapsed < self._update_freq:
            await asyncio.sleep(self._update_freq - delay_elapsed)

    async def update_loop(self):
        while not self.stop_update:
            try:
                await self.cancelable(self.update_round())
            except asyncio.CancelledError:
                self._cancel_event.clear()

    def interrupt(self) -> None:
        def cancel():
            self._cancel_event.set()

        self._loop.call_soon_threadsafe(cancel)

    def update_now(self) -> None:
        self.interrupt()

    def start(self) -> None:
        self.stop_update = False
        self._loop = asyncio.new_event_loop()
        # self._loop.set_debug(True)
        self._cancel_event = asyncio.Event(loop=self._loop)

        def _run_update_loop(loop):
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.update_loop())

        self._update_thread = Thread(target=_run_update_loop, args=(self._loop,), daemon=True)
        self._update_thread.start()

    def terminate(self) -> None:
        self.stop_update = True
        self.interrupt()
        self._update_thread.join()

    @property
    def last_results(self) -> Iterable[Tuple[ScanResult, Optional[datetime], int]]:
        return zip(self._last_results, self._last_stock_time, self._consecutive_errors)

    @property
    def scanners(self) -> List[Scanner]:
        return self._scanners
