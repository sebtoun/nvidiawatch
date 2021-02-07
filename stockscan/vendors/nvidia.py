from stockscan.scanner import SearchBasedHttpScanner
from typing import List


class NvidiaScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "Nvidia"
        super().__init__(name, search_terms, **kwargs)

    @property
    def request_headers(self) -> dict:
        headers = {
            # "origin": "https://www.nvidia.com",
            # "referer": "https://www.nvidia.com/",
            # "dnt": "1",
            # "accept": "application/json,text/plain,*/*",
            # "accept-encoding": "gzip, deflate, br",
            # "accept-language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            # "cache-control": "max-age=0"
        }
        headers.update(super().request_headers)
        return headers

    @property
    def target_url(self) -> str:
        return "https://api.nvidia.partners/edge/product/search?page=1&limit=9&locale=fr-fr&manufacturer=NVIDIA"

    def _get_all_items_in_page(self, json: dict) -> List[dict]:
        products = list(json["searchedProducts"]["productDetails"])
        if json["searchedProducts"]["featuredProduct"] is not None:
            products.append(json["searchedProducts"]["featuredProduct"])
        return products

    def _get_item_title(self, item: dict, json: dict) -> str:
        return item["productTitle"]

    def _get_item_price(self, item: dict, content: dict) -> float:
        return float(item["productPrice"].replace('€', '').replace(',', ''))

    def _is_item_in_stock(self, item: dict, json: dict) -> bool:
        return item["prdStatus"] != "out_of_stock"

    def _get_item_url(self, item: dict, content: dict) -> str:
        try:
            return item["retailers"][0]["directPurchaseLink"]
        except:
            return self.user_url

    @property
    def user_url(self) -> str:
        return "https://www.nvidia.com/fr-fr/shop/geforce/?page=1&limit=9&locale=fr-fr&manufacturer=NVIDIA"
