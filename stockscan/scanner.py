from typing import Dict, Union, List, Tuple, Iterable
from datetime import datetime
from bs4 import BeautifulSoup
from bs4.element import Tag
from json.decoder import JSONDecodeError
from concurrent.futures import ThreadPoolExecutor, Future

import requests
import threading
import time

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 " \
             "Safari/537.36 "


def make_soup(resp: requests.Response):
    return BeautifulSoup(resp.content, 'html.parser')


def parse_search_terms(search_terms: str) -> Tuple[List[str], List[str]]:
    terms = list(filter(None, search_terms.lower().split(" ")))
    keywords: List[str] = []
    blacklist: List[str] = []
    for term in terms:
        if term.startswith("-"):
            blacklist.append(term[1:])
        else:
            keywords.append(term)
    return keywords, blacklist


class Scanner:
    Item = Tuple[str, float, bool]

    DefaultTimeout = 3

    InStock = "in_stock"
    Unavailable = "unavailable"
    Error = "error"

    def __init__(self, name: str):
        self._last_state = Scanner.Unavailable
        self._last_scan_time_per_state: Dict[str, Union[datetime, None]] = {
            Scanner.InStock: None,
            Scanner.Unavailable: None,
            Scanner.Error: None
        }
        self._last_scan_time = None
        self._last_error = None
        self._consecutive_errors = 0
        self._name = name

    def _scan(self) -> None:
        raise Exception("Not Implemented")

    @property
    def items(self) -> List[Item]:
        raise Exception("Not Implemented")

    @property
    def watched_item_count(self) -> int:
        return len(self.items)

    def update(self) -> str:
        try:
            self._scan()
            if any(stock for _, _, stock in self.items):
                self._last_state = Scanner.InStock
            else:
                self._last_state = Scanner.Unavailable
            self._consecutive_errors = 0
        except Exception as exc:
            self._last_state = Scanner.Error
            self._last_error = exc
            self._consecutive_errors += 1
        self._last_scan_time = self._last_scan_time_per_state[self._last_state] = datetime.now()
        return self._last_state

    @property
    def user_url(self) -> str:
        raise Exception("Not Implemented")

    @property
    def name(self) -> str:
        return self._name

    @property
    def last_stock_time(self) -> datetime:
        return self._last_scan_time_per_state[Scanner.InStock]

    @property
    def last_error_time(self) -> datetime:
        return self._last_scan_time_per_state[Scanner.Error]

    @property
    def last_unavailable_time(self) -> datetime:
        return self._last_scan_time_per_state[Scanner.Unavailable]

    @property
    def last_scan_time(self) -> datetime:
        return self._last_scan_time

    @property
    def in_stock(self) -> bool:
        return self._last_state is Scanner.InStock

    @property
    def consecutive_errors(self) -> int:
        return self._consecutive_errors

    @property
    def has_error(self) -> bool:
        return self._last_state is Scanner.Error

    @property
    def last_error(self) -> Exception:
        return self._last_error

    @property
    def last_sate(self) -> str:
        return self._last_state

    def clear_last_error(self) -> None:
        self._last_error = None


class HttpScanner(Scanner):
    PageEntry = Union[dict, Tag]
    Page = Union[dict, BeautifulSoup]

    def __init__(self, name: str, method='GET', **kwargs):
        super().__init__(name)
        self.method = method
        self.time_out = kwargs.get("time_out", Scanner.DefaultTimeout)
        self._items = []

    @property
    def target_url(self) -> str:
        raise Exception("Not Implemented")

    @property
    def items(self) -> List[Scanner.Item]:
        return self._items

    def _get_all_items_in_page(self, content: Page) -> PageEntry:
        raise Exception("Not Implemented")

    def _get_item_title(self, item: PageEntry, content: Page) -> str:
        raise Exception("Not Implemented")

    def _is_item_in_stock(self, item: PageEntry, content: Page) -> bool:
        raise Exception("Not Implemented")

    def _get_item_price(self, item: PageEntry, content: Page) -> float:
        raise Exception("Not Implemented")

    def filter_item(self, item: Scanner.Item) -> bool:
        return True

    @property
    def payload(self) -> Union[str, dict]:
        return ''

    def _get_item(self, entry: PageEntry, page: Page) -> Scanner.Item:
        item = (self._get_item_title(entry, page),
                self._get_item_price(entry, page),
                self._is_item_in_stock(entry, page))
        return item

    def _scan_response(self, content: Page) -> None:
        entries = self._get_all_items_in_page(content)
        self._items = [item for item in (self._get_item(entry, content) for entry in entries) if self.filter_item(item)]

    @property
    def request_headers(self) -> dict:
        return {'user-agent': USER_AGENT}

    def _scan(self) -> None:
        if self.method == 'GET':
            request_method = requests.get
        elif self.method == 'POST':
            request_method = requests.post
        else:
            raise ValueError(f"Unsupported method: {self.method}")
        resp = request_method(self.target_url, headers=self.request_headers, data=self.payload, timeout=self.time_out)
        resp.raise_for_status()
        try:
            content = resp.json()
        except JSONDecodeError:
            content = make_soup(resp)

        self._scan_response(content)

    @property
    def user_url(self) -> str:
        return self.target_url


class SearchBasedHttpScanner(HttpScanner):
    def __init__(self, name: str, search_terms: str, **kwargs):
        self._keywords, self._blacklist = parse_search_terms(search_terms)
        self._item_count = 0
        super().__init__(name, **kwargs)

    def filter_item(self, item: Scanner.Item) -> bool:
        return self.is_title_valid(item[0])

    def is_title_valid(self, item_title: str) -> bool:
        keywords = self._keywords
        blacklist = self._blacklist
        text = item_title.lower()
        return all(k in text for k in keywords) and not any(k in text for k in blacklist)

    @property
    def name(self) -> str:
        return f"{super().name}[{'+'.join(self._keywords)}]"


class StockMonitor:
    def __init__(self, scanners: List[Scanner], update_freq=10, max_thread=8):
        self._update_freq = update_freq
        self._scanners = scanners
        self._update_results: Union[Iterable[Future], None] = None
        self._last_update_time = None
        self._update_requested = False

        # update thread
        self.pool = ThreadPoolExecutor(min(max_thread, len(scanners)))
        self._update_thread = None
        self.stop_update = False

    def _update_scanners(self):
        def update_scanner(scanner: Scanner):
            scanner.update()

        self._last_update_time = datetime.now()
        self._update_results = [self.pool.submit(update_scanner, scanner) for scanner in self._scanners]
        self._update_requested = False

    def _update_loop(self):
        self._update_scanners()
        while not self.stop_update:
            update_pending = any(map(lambda f: not f.done(), self._update_results))
            delay_elapsed = (datetime.now() - self._last_update_time).total_seconds() >= self._update_freq
            if not update_pending and (delay_elapsed or self._update_requested):
                self._update_scanners()
            else:
                time.sleep(0.5)

    def clear_errors(self):
        for scanner in self._scanners:
            scanner.clear_last_error()

    def update_now(self):
        self._update_requested = True

    def start(self):
        assert self._update_thread is None, "Thread already running"
        self.stop_update = False
        self._update_thread = threading.Thread(target=self._update_loop)
        self._update_thread.start()

    def terminate(self):
        if self._update_thread is not None:
            self.stop_update = True
            self._update_thread.join()
        self.pool.shutdown(wait=False)
        if self._update_results is not None:
            for f in self._update_results:
                if not f.done():
                    f.cancel()

    @property
    def scanners(self):
        return self._scanners
