import asyncio
import logging

from typing import Optional, List, Tuple, Iterable
from stockscan.scanner import Scanner, ScanResult
from datetime import datetime
from threading import Thread
from contextlib import contextmanager

logger = logging.getLogger(__name__)


async def update_scanner(scanner):
    return await scanner.scan()


class InterruptEvent(Exception):
    def __init__(self):
        super().__init__("Interrupted by user")


class StockMonitor:
    def __init__(self, scanners: List[Scanner], update_freq=30):
        self._update_freq = update_freq
        self._scanners = scanners
        self._last_update_time = None

        # scan results
        now = datetime.now()
        self._last_results: List[ScanResult] = [ScanResult(now)] * len(scanners)
        self._last_stock_time: List[Optional[datetime]] = [None] * len(scanners)
        self._consecutive_errors: List[int] = [0] * len(scanners)

        # scan events
        self._scan_event_callbacks = set()

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
            await self.dispatch_scan_event(self._scanners[i], result,
                                           self._last_stock_time[i], self._consecutive_errors[i])

    async def interruptible(self, coro):
        done, pending = await asyncio.wait([coro, self._cancel_event.wait()], return_when=asyncio.FIRST_COMPLETED)
        try:
            if self._cancel_event.is_set():
                raise InterruptEvent()
            else:
                return next(iter(done)).result()
        finally:
            for task in pending:
                task.cancel()
            cancel_task = asyncio.gather(*pending, return_exceptions=True)
            await cancel_task

    async def update_round(self, sleep=True):
        # trigger new update
        self._last_update_time = datetime.now()
        await self._update_scanners()
        if sleep:
            # wait remaining time
            delay_elapsed = (datetime.now() - self._last_update_time).total_seconds()
            if delay_elapsed < self._update_freq:
                await asyncio.sleep(self._update_freq - delay_elapsed)

    async def dispatch_scan_event(self, scanner: Scanner, result: ScanResult, last_stock_time: Optional[datetime],
                                  consecutive_errors: int):
        for fun in self._scan_event_callbacks:
            try:
                await fun(scanner, result, last_stock_time, consecutive_errors)
            except Exception as err:
                logger.exception("Exception during scan event dispatch", err)

    def register_to_scan(self, callback):
        self._scan_event_callbacks.add(callback)

    def unregister_from_scan(self, callback):
        self._scan_event_callbacks.remove(callback)

    async def single_update(self):
        self._loop = asyncio.get_running_loop()
        self._cancel_event = asyncio.Event()
        try:
            await self.interruptible(self.update_round(sleep=False))
        except InterruptEvent:
            self._cancel_event.clear()

    async def update_loop(self):
        self._loop = asyncio.get_running_loop()
        self._cancel_event = asyncio.Event()
        while not self.stop_update:
            try:
                await self.interruptible(self.update_round())
            except InterruptEvent:
                self._cancel_event.clear()

    def interrupt(self) -> None:
        def cancel():
            self._cancel_event.set()

        self._loop.call_soon_threadsafe(cancel)

    def update_now(self) -> None:
        self.interrupt()

    def start_in_thread(self) -> None:
        logger.debug('start thread')
        self.stop_update = False

        def _run_update_loop():
            asyncio.run(self.update_loop())

        self._update_thread = Thread(target=_run_update_loop, daemon=True)
        self._update_thread.start()
        logger.debug('thread started')

    def terminate(self) -> None:
        logger.debug('terminate thread')
        self.stop_update = True
        self.interrupt()
        self._update_thread.join()
        logger.debug('thread joined')

    @contextmanager
    def running_in_thread(self):
        self.start_in_thread()
        try:
            yield
        finally:
            self.terminate()

    @property
    def last_results(self) -> Iterable[Tuple[ScanResult, Optional[datetime], int]]:
        return zip(self._last_results, self._last_stock_time, self._consecutive_errors)

    @property
    def scanners(self) -> List[Scanner]:
        return self._scanners
