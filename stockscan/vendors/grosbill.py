from stockscan.scanner import SearchBasedHttpScanner
from typing import List
from urllib.parse import quote
from bs4 import BeautifulSoup
from bs4.element import Tag


class GrosBillScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "GrosBill"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.grosbill.com/catv2.cgi?mode=recherche&recherche={quote(' '.join(self._keywords))}"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".diaporama_mode_display div[id]") or bs.select(".datasheet_container")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> Tag:
        title = item.select_one(".product_description h2") or item.select_one("h1[itemprop=name]")
        assert title, "Item title not found"
        return title.get_text().strip()

    def _get_item_price(self, item: Tag, bs: BeautifulSoup) -> float:
        price = item.select_one(".btn_price_wrapper b")
        if price is not None:
            return float(price.get_text().strip().replace("€", "."))
        price = item.select_one("b[itemprop=price]")
        assert price is not None, "could not get price"
        return float(price.attrs["content"])

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        stock = item.select_one(".btn_en_stock_wrapper")
        if stock is not None:
            return stock.get_text().strip().upper() == "EN STOCK"
        stock = item.select_one("link[itemprop=availability]")
        if stock is not None:
            return stock.attrs["href"] == "https://schema.org/InStock"
        return False
