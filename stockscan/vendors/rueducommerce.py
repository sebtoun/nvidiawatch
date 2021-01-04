from stockscan.scanner import SearchBasedHttpScanner
from typing import List
from urllib.parse import quote


class RueDuCommerceScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "RueDuCommerce"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return "https://www.rueducommerce.fr/listingDyn?" \
               f"boutique_id=18&langue_id=1&recherche={quote('-'.join(self._keywords))}&from=0"

    def _get_all_items_in_page(self, json: dict) -> List[dict]:
        return json["produits"]

    def _get_item_title(self, item: dict, json: dict) -> str:
        return f"{item['fournisseur_nom']} - {item['produit_nom_nom']}"

    def _get_item_price(self, item: dict, json: dict) -> str:
        return item["produit_prix_ttc"]

    def _is_item_in_stock(self, item: dict, json: dict) -> bool:
        assert item["shop_name"] == "Rue du Commerce", f"Wrong shop name: {item['shop_name']}"
        return item["Disponibilite"] == "en stock"

    @property
    def user_url(self) -> str:
        return f"https://www.rueducommerce.fr/r/{quote('-'.join(self._keywords))}.html"
