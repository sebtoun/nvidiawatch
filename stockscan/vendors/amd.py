from stockscan.scanner import SearchBasedHttpScanner
from typing import List
from urllib.parse import quote
from yarl import URL
from bs4 import BeautifulSoup
from bs4.element import Tag


class AMDScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "AMD"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return "https://www.amd.com/fr/direct-buy/fr"

    @property
    def cookies(self) -> dict:
        return {"pmuser_country": "fr"}

    @property
    def request_headers(self) -> dict:
        headers = super().request_headers
        headers.update({"accept-language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"})
        return headers

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".view-shop-product-search .shop-content")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.select_one(".shop-title").get_text().strip()

    def _get_item_price(self, item: Tag, json: dict) -> float:
        return float(item.select_one('.shop-price').get_text().replace('€', '').replace(',', '.').strip())

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return item.select_one(".shop-links button") is not None

    def _get_item_url(self, item: Tag, bs: BeautifulSoup) -> str:
        return self.request_url.join(URL(item.select_one(".shop-details a").attrs["href"])).human_repr()
