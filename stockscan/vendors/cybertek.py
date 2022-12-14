from stockscan.scanner import SearchBasedHttpScanner
from typing import List
from urllib.parse import quote
from bs4 import BeautifulSoup
from bs4.element import Tag


class CybertekScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "Cybertek"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.cybertek.fr/boutique/produit.aspx?q={quote('+'.join(self._keywords))}"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".liste-produits .lst_grid > div")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.select_one(".nom-produit h2").get_text().strip()

    def _get_item_price(self, item: Tag, json: dict) -> float:
        return float(item.select_one('.prix-produit').get_text().replace('€', '.').strip())

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return "listing_dispo" in item["class"]

    def _get_item_url(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.find("a", recursive=False).attrs["href"]
