from stockscan.scanner import SearchBasedHttpScanner
from typing import List
from urllib.parse import quote
from bs4 import BeautifulSoup
from bs4.element import Tag
from yarl import URL

import json
import re


class HardwareFrScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "HardwareFr"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://shop.hardware.fr/search/+ftxt-{quote('-'.join(self._keywords))}/"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".list li[data-ref]") or bs.select("div#infosProduit")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        title = item.select(".description h2,#description h1")
        assert len(title) == 1, "Item title not found"
        return title[0].get_text()

    def _get_item_price(self, item: Tag, bs: BeautifulSoup) -> float:
        item_id = item.attrs["id"]
        if item_id == "infosProduit":  # single element page
            metadata = bs.find("script", attrs={'type': 'application/ld+json'})
            assert metadata, "Could not find price"
            metadata_json = json.loads(metadata.string)
            assert self.is_title_valid(metadata_json["name"]), "Wrong item metadata"
            return float(metadata_json["offers"]["price"])
        else:  # multiple results page
            script_data = ''.join(s.string for s in bs.find_all("script", attrs={"src": None}))
            price_html = re.search(
                "#{id}\s+\.price-wrapper.*?replaceWith\('<span class=\"prix\">(.*?)</span>'\)".format(id=item_id),
                script_data)[1]
            return float(BeautifulSoup(price_html, "html.parser").get_text().strip().replace('€', '.'))

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        item_id = item.attrs["id"]
        if item_id == "infosProduit":  # single element page
            metadata = bs.find("script", attrs={'type': 'application/ld+json'})
            assert metadata, "Could not find stock status"
            metadata_json = json.loads(metadata.string)
            assert self.is_title_valid(metadata_json["name"]), "Wrong item metadata"
            return metadata_json["offers"]["availability"] in [
                'http://schema.org/InStock', 'http://schema.org/OnlineOnly', 'http://schema.org/LimitedAvailability']
        else:  # multiple results page
            script_data = ''.join(s.string for s in bs.find_all("script", attrs={"src": None}))
            stock_type = int(re.search("#{id}\s+\.stock-wrapper.*?stock-([0-9])".format(id=item_id), script_data)[1])
            return stock_type <= 2

    def _get_item_url(self, item: Tag, content: BeautifulSoup) -> str:
        link = item.findChild("a")
        if link is not None:
            return self.request_url.join(URL(link.attrs["href"])).human_repr()
        return self.request_url.human_repr()
