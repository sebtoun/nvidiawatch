from stockscan.scanner import SearchBasedHttpScanner
from typing import List, Optional
from urllib.parse import quote
from bs4 import BeautifulSoup
from bs4.element import Tag
from yarl import URL
import re

class LDLCScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, custom_url: Optional[str] = None, **kwargs):
        name = "LDLC"
        self.custom_url = custom_url
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return self.custom_url or f"https://www.ldlc.com/recherche/{quote(' '.join(self._keywords))}/"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".listing-product .pdt-item") or bs.select(".product-bloc")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> Tag:
        title = item.find(class_="title-3") or item.find(class_="title-1")
        assert title, "Item title not found"
        return title.get_text()

    def _get_item_price(self, item: Tag, bs: BeautifulSoup) -> float:
        price = item.select_one(".price").get_text().strip()
        if price:
            return float(price.replace('€', '.').replace('\xa0', ''))
        else:
            script_data = ''.join(s.string for s in bs.find_all("script", attrs={"src": None}))
            match = re.search(
                "#{id}\s+\.price.*?replaceWith\('<div class=\"price\">(.*?)</div>'\)".format(id=item.attrs["id"]),
                script_data)
            if match:
                price = BeautifulSoup(match[1], "html.parser").get_text().strip()
                return float(price.replace('€', '.').replace('\xa0', ''))
        assert False, "could not parse price"

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return len(item.select(".stock-web .stock-1,.stock-web .stock-2")) > 0

    def _get_item_url(self, item: Tag, content: BeautifulSoup) -> str:
        link = item.select_one(".pdt-desc a")
        if link is not None:
            return self.request_url.join(URL(link.attrs["href"])).human_repr()
        return self.request_url.human_repr()
