from stockscan.scanner import SearchBasedHttpScanner
from typing import List
from urllib.parse import quote
from bs4 import BeautifulSoup
from bs4.element import Tag
from yarl import URL


class TopAchatScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "TopAchat"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.topachat.com/pages/recherche.php?cat=micro&etou=0&mc={quote('+'.join(self._keywords))}"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        items = bs.select('.produits.list article')
        if not items:
            product = bs.select_one('.product-sheet')
            if product is not None:
                items.append(product.parent)
        return items

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        title = item.select(".libelle h1, .libelle h2, .libelle h3")
        assert title, "Item title not found"
        return title[0].get_text()

    def _get_item_price(self, item: Tag, bs: BeautifulSoup) -> float:
        return float(item.select_one(".prod_px_euro,.priceFinal.fp44").get_text().replace('€', '').strip())

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return item.find(class_="en-stock") is not None

    def _get_item_url(self, item: Tag, content: BeautifulSoup) -> str:
        link = item.select_one(".libelle a")
        if link is not None:
            return self.request_url.join(URL(link.attrs["href"])).human_repr()
        return self.request_url.human_repr()
