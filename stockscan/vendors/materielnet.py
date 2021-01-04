from stockscan.scanner import SearchBasedHttpScanner
from typing import List
from bs4 import BeautifulSoup
from bs4.element import Tag
from urllib.parse import quote

import requests
import re
import json


class MaterielNetScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "MaterielNet"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.materiel.net/recherche/{quote('+'.join(self._keywords))}/"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select("ul.c-products-list li.c-products-list__item") or bs.select("#tpl__product-page")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        title = item.select(".c-products-list__item .c-product__title, .c-product__header h1")
        assert len(title) == 1, "Multiple item title found or no title found"
        return title[0].get_text()

    def _is_item_in_stock(self, item: str, bs: BeautifulSoup) -> bool:
        match = re.search(r"o-availability__value--stock_([0-9])", item)
        assert match, "Failed to match string looking for stock"
        return int(match[1]) <= 2

    def _check_stocks(self, items: List[SearchBasedHttpScanner.Item], content: SearchBasedHttpScanner.Content) -> bool:
        stock_query_url = "https://www.materiel.net/product-listing/stock-price/"

        def get_item_id(item: Tag):
            return item.select_one("[data-offer-id]").attrs["data-offer-id"]

        query_offers = [{"offerId": get_item_id(item), "marketplace": False} for item in items]
        stock_query_payload = {
            "json": json.dumps({
                "currencyISOCode3": "EUR",
                "offers": query_offers,
                "shops": [
                    {"shopId": -1}]
            })
        }
        headers = dict(self.request_headers)
        headers.update({'x-requested-with': 'XMLHttpRequest'})
        resp = requests.post(stock_query_url, data=stock_query_payload, headers=headers)
        resp.raise_for_status()
        item_stocks = list(resp.json()["stock"].values())

        def is_in_stock(item: str) -> bool:
            return self._is_item_in_stock(item, content)

        return any(map(is_in_stock, item_stocks))
