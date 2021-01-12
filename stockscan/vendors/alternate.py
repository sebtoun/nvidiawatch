from stockscan.scanner import SearchBasedHttpScanner
from typing import List
from urllib.parse import quote
from bs4 import BeautifulSoup
from bs4.element import Tag
from yarl import URL


class AlternateScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, locale="fr", **kwargs):
        self._locale = locale.lower()
        name = "Alternate" + locale.upper()
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.alternate.{self._locale}/html/search.html?query={quote(' '.join(self._keywords))}"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".listingContainer .listRow")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.find(class_="productLink").attrs["title"]

    def _get_item_price(self, item: Tag, content: BeautifulSoup) -> float:
        def parse_price(text: str) -> float:
            return float(text.replace('*', '').replace('€', '')
                         .replace('.', '').replace(',', '.').replace('-', '0').strip())

        return parse_price(item.select_one(".price").get_text())

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return item.select_one(".stockStatus.available_stock") is not None

    def _get_item_url(self, item: Tag, content: BeautifulSoup) -> str:
        return self.request_url.join(URL(item.find(class_="productLink").attrs["href"])).human_repr()
