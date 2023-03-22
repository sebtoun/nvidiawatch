from typing import Optional, Union, List, Tuple, Dict
from datetime import datetime
from bs4 import BeautifulSoup
from bs4.element import Tag
from json.decoder import JSONDecodeError
from dataclasses import dataclass
from aiohttp import ClientTimeout, ContentTypeError

import aiohttp

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 " \
             "Safari/537.36 "

ALL_SCANNERS = {}


def make_soup(content):
    return BeautifulSoup(content, 'html.parser')


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
    url: str


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

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "error": self.error,
            "items": self.items
        }


class MetaScanner(type):
    def __new__(cls, name, bases, namespace, **kargs):
        return super(MetaScanner, cls).__new__(cls, name, bases, namespace)

    def __init__(cls, name, bases, namespace, is_concrete_scanner=True):
        super(MetaScanner, cls).__init__(name, bases, namespace)
        if is_concrete_scanner:
            ALL_SCANNERS[name.lower()] = cls


class Scanner(metaclass=MetaScanner, is_concrete_scanner=False):
    def __init__(self, name: str):
        self._name = name

    async def _scan(self) -> List[Item]:
        raise Exception("Not Implemented")

    async def scan(self) -> ScanResult:
        try:
            items = await self._scan()
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


class HttpScanner(Scanner, is_concrete_scanner=False):
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

    def _get_item_url(self, item: PageEntry, content: Page) -> str:
        return self.user_url

    def filter_item(self, item: Item) -> bool:
        return True

    @property
    def payload(self) -> Union[str, dict]:
        return ''

    def _get_item(self, entry: PageEntry, page: Page) -> Item:
        item = Item(title=self._get_item_title(entry, page),
                    price=self._get_item_price(entry, page),
                    in_stock=self._is_item_in_stock(entry, page),
                    url=self._get_item_url(entry, page))
        return item

    async def _scan_response(self, content: Page) -> List[Item]:
        entries = self._get_all_items_in_page(content)
        return [item for item in (self._get_item(entry, content) for entry in entries) if self.filter_item(item)]

    @property
    def request_headers(self) -> dict:
        return {'user-agent': USER_AGENT}

    @property
    def cookies(self) -> dict:
        return {}

    async def _scan(self):
        if self.method not in ['GET', 'POST']:
            raise ValueError(f"Unsupported method: {self.method}")

        async with aiohttp.ClientSession(headers=self.request_headers,
                                         cookies=self.cookies,
                                         raise_for_status=True,
                                         timeout=ClientTimeout(total=self.time_out)) as session:
            if self.method == 'GET':
                request_method = session.get
            elif self.method == 'POST':
                request_method = session.post
            async with request_method(self.target_url, data=self.payload) as resp:
                try:
                    content = await resp.json()
                except (JSONDecodeError, ContentTypeError):
                    text = await resp.text()
                    content = make_soup(text)
                self.request_url = resp.url
                return await self._scan_response(content)

    @property
    def user_url(self) -> str:
        return self.target_url


class SearchBasedHttpScanner(HttpScanner, is_concrete_scanner=False):
    def __init__(self, name: str, search_terms: str, **kwargs):
        self._keywords, self._blacklist = parse_search_terms(search_terms)
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
