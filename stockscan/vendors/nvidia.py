from stockscan.scanner import SearchBasedHttpScanner
from typing import List


class NvidiaScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "Nvidia"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return "https://api.nvidia.partners/edge/product/search?page=1&limit=100&locale=fr-fr&manufacturer=NVIDIA"

    def _get_all_items_in_page(self, json: dict) -> List[dict]:
        products = list(json["searchedProducts"]["productDetails"])
        products.append(json["searchedProducts"]["featuredProduct"])
        return products

    def _get_item_title(self, item: dict, json: dict) -> str:
        return item["productTitle"]

    def _get_item_price(self, item: dict, content: dict) -> str:
        return item["productPrice"]

    def _is_item_in_stock(self, item: dict, json: dict) -> bool:
        return item["prdStatus"] != "out_of_stock"

    @property
    def user_url(self) -> str:
        return "https://www.nvidia.com/fr-fr/shop/geforce/?page=1&limit=9&locale=fr-fr&manufacturer=NVIDIA"
