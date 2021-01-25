from typing import List
from .scanner import Scanner, Item
import random
import asyncio


class DummyException(RuntimeError):
    def __init__(self):
        super().__init__("Dummy exception veryyyy long" * 5)


class DummyScanner(Scanner, is_concrete_scanner=False):
    def __init__(self, stocks=1, unavailable=1, error=1, delay=1):
        super().__init__("Dummy")
        self._weights = [stocks, unavailable, error]
        self._delay = delay

    @property
    def user_url(self) -> str:
        return "http://www.dummy.com/"

    async def _scan(self) -> List[Item]:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        outcome = random.choices([True, False, DummyException()], self._weights)[0]
        if isinstance(outcome, DummyException):
            raise outcome
        return [Item(title="Dummy item", price=99.99, in_stock=outcome)]

    @property
    def name(self) -> str:
        return f"{super().name}[delay={self._delay} weights={self._weights}]"
