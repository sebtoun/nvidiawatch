from stockscan.scanner import SearchBasedHttpScanner
from typing import List
from urllib.parse import quote
from bs4 import BeautifulSoup
from bs4.element import Tag


class CaseKingScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "CaseKing"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.caseking.de/en/search?sSearch={quote('+'.join(self._keywords))}"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".artbox")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.find(class_="producttitles").attrs["data-description"]

    def _get_item_price(self, item: Tag, bs: BeautifulSoup) -> float:
        def parse_price(text: str) -> float:
            return float(text.replace('€', '').replace(',', '').replace('*', ''))

        return parse_price(item.select_one(".price").get_text().strip())

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return item.find(class_="deliverable1") is not None
