import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
import re
from datetime import datetime
import time
import random
from typing import Dict, Union, List, Tuple
from urllib.parse import quote
import json
from json.decoder import JSONDecodeError


def make_soup(resp: requests.Response):
    return BeautifulSoup(resp.content, 'html.parser')


def parse_search_terms(search_terms: str) -> Tuple[List[str], List[str]]:
    terms = list(filter(None, search_terms.lower().split(" ")))
    keywords: List[str] = []
    blacklist: List[str] = []
    for term in terms:
        if term.startswith("-"):
            blacklist.append(term[1:])
        else:
            keywords.append(term)
    return keywords, blacklist


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 " \
             "Safari/537.36 "


class Scanner:
    DefaultTimeout = 3

    InStock = "in_stock"
    Unavailable = "unavailable"
    Error = "error"

    def __init__(self, name: str):
        self._last_state = Scanner.Unavailable
        self._last_scan_time_per_state: Dict[str, Union[datetime, None]] = {
            Scanner.InStock: None,
            Scanner.Unavailable: None,
            Scanner.Error: None
        }
        self._last_scan_time = None
        self._last_error = None
        self._consecutive_errors = 0
        self._name = name

    def _scan(self) -> bool:
        raise Exception("Not Implemented")

    @property
    def watched_item_count(self) -> int:
        raise Exception("Not Implemented")

    def get_details(self) -> List[Tuple[str, str, bool]]:
        raise Exception("Not Implemented")

    def update(self) -> None:
        try:
            if self._scan():
                self._last_state = Scanner.InStock
            else:
                self._last_state = Scanner.Unavailable
            self._consecutive_errors = 0
        except Exception as exc:
            self._last_state = Scanner.Error
            self._last_error = exc
            self._consecutive_errors += 1
        self._last_scan_time = self._last_scan_time_per_state[self._last_state] = datetime.now()

    @property
    def user_url(self) -> str:
        raise Exception("Not Implemented")

    @property
    def name(self) -> str:
        return self._name

    @property
    def last_stock_time(self) -> datetime:
        return self._last_scan_time_per_state[Scanner.InStock]

    @property
    def last_error_time(self) -> datetime:
        return self._last_scan_time_per_state[Scanner.Error]

    @property
    def last_unavailable_time(self) -> datetime:
        return self._last_scan_time_per_state[Scanner.Unavailable]

    @property
    def last_scan_time(self) -> datetime:
        return self._last_scan_time

    @property
    def in_stock(self) -> bool:
        return self._last_state is Scanner.InStock

    @property
    def consecutive_errors(self) -> int:
        return self._consecutive_errors

    @property
    def has_error(self) -> bool:
        return self._last_state is Scanner.Error

    @property
    def last_error(self) -> Exception:
        return self._last_error

    @property
    def last_sate(self) -> str:
        return self._last_state

    def clear_last_error(self) -> None:
        self._last_error = None


class DummyException(RuntimeError):
    def __init__(self):
        super().__init__("Dummy exception")


class DummyScanner(Scanner):
    def __init__(self, stocks=1, unavailable=1, error=1, delay=1):
        super().__init__("Dummy")
        self._weights = [stocks, unavailable, error]
        self._delay = delay

    @property
    def user_url(self) -> str:
        return "http://www.dummy.com/"

    def _scan(self) -> bool:
        if self._delay > 0:
            time.sleep(self._delay)
        outcome = random.choices([True, False, DummyException()], self._weights)[0]
        if isinstance(outcome, DummyException):
            raise outcome
        return outcome


class HttpScanner(Scanner):
    def __init__(self, name: str, method='GET', **kwargs):
        super().__init__(name)
        self.method = method
        self.time_out = kwargs.get("time_out", Scanner.DefaultTimeout)

    @property
    def target_url(self) -> str:
        raise Exception("Not Implemented")

    @property
    def payload(self) -> Union[str, dict]:
        return ''

    def _scan_response(self, resp: requests.Response) -> bool:
        raise Exception("Not Implemented")

    @property
    def request_headers(self) -> dict:
        return {'user-agent': USER_AGENT}

    def _scan(self) -> bool:
        if self.method == 'GET':
            request_method = requests.get
        elif self.method == 'POST':
            request_method = requests.post
        else:
            raise ValueError(f"Unsupported method: {self.method}")
        resp = request_method(self.target_url, headers=self.request_headers, data=self.payload, timeout=self.time_out)
        resp.raise_for_status()
        return self._scan_response(resp)

    @property
    def user_url(self) -> str:
        return self.target_url


class SearchBasedHttpScanner(HttpScanner):
    Item = Union[dict, Tag]
    Content = Union[dict, BeautifulSoup]

    def __init__(self, name: str, search_terms: str, **kwargs):
        self._keywords, self._blacklist = parse_search_terms(search_terms)
        super().__init__(name, **kwargs)

    def _get_all_items_in_page(self, content: Content) -> List[Item]:
        raise Exception("Not Implemented")

    def _get_item_title(self, item: Item, content: Content) -> str:
        raise Exception("Not Implemented")

    def _is_item_in_stock(self, item: Item, content: Content) -> bool:
        raise Exception("Not Implemented")

    def _get_item_price(self, item: Item, content: Content) -> str:
        raise Exception("Not Implemented")

    def _check_stocks(self, items: List[Item], content: Content) -> bool:
        def is_in_stock(item: SearchBasedHttpScanner.Item) -> bool:
            return self._is_item_in_stock(item, content)

        return any(map(is_in_stock, items))

    def _filter_result(self, content: Content) -> List[Item]:
        def is_wanted(item: SearchBasedHttpScanner.Item) -> bool:
            title = self._get_item_title(item, content)
            assert bool(title), "Item title not found"
            return self.is_title_valid(title)

        return list(filter(is_wanted, self._get_all_items_in_page(content)))

    def is_title_valid(self, item_title: str) -> bool:
        keywords = self._keywords
        blacklist = self._blacklist
        text = item_title.lower()
        return all(k in text for k in keywords) and not any(k in text for k in blacklist)

    def _scan_response(self, resp: requests.Response) -> bool:
        try:
            content = resp.json()
        except JSONDecodeError:
            content = make_soup(resp)

        items = self._filter_result(content)
        self._item_count = len(items)
        assert self._item_count > 0, "No valid item found"

        return self._check_stocks(items, content)

    @property
    def watched_item_count(self) -> int:
        return self._item_count or None

    @property
    def name(self) -> str:
        return f"{super().name}[{'+'.join(self._keywords)}]"


class LDLCScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "LDLC"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.ldlc.com/recherche/{quote('+'.join(self._keywords))}/"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".listing-product .pdt-item") or bs.select(".product-bloc")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> Tag:
        title = item.find(class_="title-3") or item.find(class_="title-1")
        assert title, "Item title not found"
        return title.get_text()

    def _get_item_price(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.select_one(".price").get_text()

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return len(item.select(".stock-web .stock-1,.stock-web .stock-2")) > 0


class TopAchatScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "TopAchat"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.topachat.com/pages/recherche.php?cat=accueil&etou=0&mc={quote('+'.join(self._keywords))}"

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

    def _get_item_price(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.select_one(".prod_px_euro,.priceFinal.fp44").get_text()

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return item.find(class_="en-stock") is not None


class HardwareFrScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "HardwareFr"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://shop.hardware.fr/search/+ftxt-{quote('-'.join(self._keywords))}/"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select("li[data-ref]") or bs.select("div#infosProduit")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        title = item.select(".description h2,#description h1")
        assert len(title) == 1, "Item title not found"
        return title[0].get_text()

    def _get_item_price(self, item: Tag, bs: BeautifulSoup) -> str:
        price = item.select_one(".prix")
        assert price, "Item price not found"
        return price.get_text().strip()

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
            stock_type = int(re.search("#{id}.*?stock-wrapper.*?stock-([0-9])".format(id=item_id), script_data)[1])
            return stock_type <= 2


class CaseKingScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "CaseKing"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.caseking.de/en/search?sSearch={quote('+'.join(self._keywords))}"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".artbox")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.find(class_="producttitles").attrs["data-description"]

    def _get_item_price(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.select_one(".price").get_text().strip()

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return item.find(class_="deliverable1") is not None


class AlternateScanner(SearchBasedHttpScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "Alternate"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.alternate.de/html/search.html?query={quote('+'.join(self._keywords))}"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".listingContainer .listRow")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.find(class_="productLink").attrs["title"]

    def _get_item_price(self, item: Tag, content: BeautifulSoup) -> str:
        return item.select_one(".price").get_text().strip()

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return item.select_one(".stockStatus.available_stock") is not None


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
