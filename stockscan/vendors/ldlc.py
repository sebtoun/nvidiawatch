from stockscan.scanner import SearchBasedHttpScanner
from typing import List
from urllib.parse import quote
from bs4 import BeautifulSoup
from bs4.element import Tag


class LDLCScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "LDLC"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.ldlc.com/recherche/{quote('+'.join(self._keywords))}/"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".listing-product .pdt-item") or bs.select(".product-bloc")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> Tag:
        title = item.find(class_="title-3") or item.find(class_="title-1")
        assert title, "Item title not found"
        return title.get_text()

    def _get_item_price(self, item: Tag, bs: BeautifulSoup) -> float:
        return float(item.select_one(".price").get_text().strip().replace('€', '.').replace('\xa0', ''))

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return len(item.select(".stock-web .stock-1,.stock-web .stock-2")) > 0
