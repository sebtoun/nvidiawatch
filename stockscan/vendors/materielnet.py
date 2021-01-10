from stockscan.scanner import SearchBasedHttpScanner, Item
from typing import List
from bs4 import BeautifulSoup
from bs4.element import Tag
from urllib.parse import quote
from aiohttp import ClientTimeout

import aiohttp
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

    async def _scan_response(self, content: BeautifulSoup) -> List[Item]:
        def get_entry_id(item: Tag):
            return item.select_one("[data-offer-id]").attrs["data-offer-id"]

        entries = {get_entry_id(entry): entry for entry in self._get_all_items_in_page(content)}
        query_offers = [{"offerId": entry_id, "marketplace": False} for entry_id in entries.keys()]
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
        stock_query_url = "https://www.materiel.net/product-listing/stock-price/"
        async with aiohttp.ClientSession(headers=headers,
                                         raise_for_status=True,
                                         timeout=ClientTimeout(total=self.time_out)) as session:
            async with session.post(stock_query_url, data=stock_query_payload) as resp:
                content_json = await resp.json()
                item_stocks = content_json["stock"]
                item_prices = content_json["price"]

        def get_price(item: str) -> float:
            return float(BeautifulSoup(item, "html.parser").get_text().strip().replace('€', '.').replace('\xa0', ''))

        def is_in_stock(item: str) -> bool:
            match = re.search(r"o-availability__value--stock_([0-9])", item)
            assert match, "Failed to match string looking for stock"
            return int(match[1]) <= 2

        return [Item(title=self._get_item_title(entry, content),
                     price=get_price(item_prices[entry_id]),
                     in_stock=is_in_stock(item_stocks[entry_id]))
                for entry_id, entry in entries.items()]
