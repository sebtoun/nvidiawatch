from .scanner import Scanner
import time
import random


class DummyException(RuntimeError):
    def __init__(self):
        super().__init__("Dummy exception")


class DummyScanner(Scanner):
    def __init__(self, stocks=1, unavailable=1, error=1, delay=1):
        super().__init__("Dummy")
        self._weights = [stocks, unavailable, error]
        self._delay = delay

    @property
    def user_url(self) -> str:
        return "http://www.dummy.com/"

    def _scan(self) -> bool:
        if self._delay > 0:
            time.sleep(self._delay)
        outcome = random.choices([True, False, DummyException()], self._weights)[0]
        if isinstance(outcome, DummyException):
            raise outcome
        return outcome
