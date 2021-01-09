from typing import Optional, Union, List, Tuple
from datetime import datetime
from bs4 import BeautifulSoup
from bs4.element import Tag
from json.decoder import JSONDecodeError
from dataclasses import dataclass

import requests

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


@dataclass
class Item:
    title: str
    price: float
    in_stock: bool


@dataclass
class ScanResult:
    timestamp: datetime = None
    error: Optional[Exception] = None
    items: Optional[List[Item]] = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @property
    def is_in_stock(self) -> bool:
        return self.items and any(item.in_stock for item in self.items)


class Scanner:
    def __init__(self, name: str):
        self._name = name

    def _scan(self) -> List[Item]:
        raise Exception("Not Implemented")

    def scan(self) -> ScanResult:
        try:
            items = self._scan()
        except Exception as err:
            items = None
            error = err
        else:
            error = None
        timestamp = datetime.now()
        return ScanResult(timestamp=timestamp,
                          items=items,
                          error=error)

    @property
    def user_url(self) -> str:
        raise Exception("Not Implemented")

    @property
    def name(self) -> str:
        return self._name


class HttpScanner(Scanner):
    PageEntry = Union[dict, Tag]
    Page = Union[dict, BeautifulSoup]

    def __init__(self, name: str, method='GET', time_out=5):
        super().__init__(name)
        self.method = method
        self.time_out = time_out

    @property
    def target_url(self) -> str:
        raise Exception("Not Implemented")

    def _get_all_items_in_page(self, content: Page) -> PageEntry:
        raise Exception("Not Implemented")

    def _get_item_title(self, item: PageEntry, content: Page) -> str:
        raise Exception("Not Implemented")

    def _is_item_in_stock(self, item: PageEntry, content: Page) -> bool:
        raise Exception("Not Implemented")

    def _get_item_price(self, item: PageEntry, content: Page) -> float:
        raise Exception("Not Implemented")

    def filter_item(self, item: Item) -> bool:
        return True

    @property
    def payload(self) -> Union[str, dict]:
        return ''

    def _get_item(self, entry: PageEntry, page: Page) -> Item:
        item = Item(title=self._get_item_title(entry, page),
                    price=self._get_item_price(entry, page),
                    in_stock=self._is_item_in_stock(entry, page))
        return item

    def _scan_response(self, content: Page) -> List[Item]:
        entries = self._get_all_items_in_page(content)
        return [item for item in (self._get_item(entry, content) for entry in entries) if self.filter_item(item)]

    @property
    def request_headers(self) -> dict:
        return {'user-agent': USER_AGENT}

    def _scan(self) -> List[Item]:
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

        return self._scan_response(content)

    @property
    def user_url(self) -> str:
        return self.target_url


class SearchBasedHttpScanner(HttpScanner):
    def __init__(self, name: str, search_terms: str, **kwargs):
        self._keywords, self._blacklist = parse_search_terms(search_terms)
        self._item_count = 0
        super().__init__(name, **kwargs)

    def filter_item(self, item: Item) -> bool:
        return self.is_title_valid(item.title)

    def is_title_valid(self, item_title: str) -> bool:
        keywords = self._keywords
        blacklist = self._blacklist
        text = item_title.lower()
        return all(k in text for k in keywords) and not any(k in text for k in blacklist)

    @property
    def name(self) -> str:
        return f"{super().name}[{'+'.join(self._keywords)}]"
