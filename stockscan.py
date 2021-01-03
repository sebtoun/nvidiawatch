import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
import re
from datetime import datetime
import time
import random
from typing import Dict, Union, List, Tuple
from urllib.parse import quote


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
        return ""

    def _scan(self) -> bool:
        if self._delay > 0:
            time.sleep(self._delay)
        outcome = random.choices([True, False, DummyException()], self._weights)[0]
        if isinstance(outcome, DummyException):
            raise outcome
        return outcome


class HtmlScanner(Scanner):
    def __init__(self, name, **kwargs):
        super().__init__(name)
        self.headers = {'user-agent': USER_AGENT}
        self.time_out = kwargs.get("time_out", Scanner.DefaultTimeout)

    @property
    def target_url(self) -> str:
        raise Exception("Not Implemented")

    def _scan_html(self, bs: BeautifulSoup) -> bool:
        raise Exception("Not Implemented")

    def _scan(self) -> bool:
        resp = requests.get(self.target_url, headers=self.headers, timeout=self.time_out)
        resp.raise_for_status()
        bs = make_soup(resp)
        return self._scan_html(bs)

    @property
    def user_url(self) -> str:
        return self.target_url


class SearchBasedHtmlScanner(HtmlScanner):
    def __init__(self, name: str, search_terms: str, **kwargs):
        self._keywords, self._blacklist = parse_search_terms(search_terms)
        super().__init__(name, **kwargs)

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        raise Exception("Not Implemented")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        raise Exception("Not Implemented")

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        raise Exception("Not Implemented")

    def _scan_html(self, bs: BeautifulSoup) -> bool:
        keywords = self._keywords
        blacklist = self._blacklist

        def is_wanted(item: Tag) -> bool:
            title = self._get_item_title(item, bs)
            assert bool(title)
            text = title.lower()
            return all(k in text for k in keywords) and not any(k in text for k in blacklist)

        items = list(filter(is_wanted, self._get_all_items_in_page(bs)))
        self._item_count = len(items)
        assert self._item_count > 0

        def is_in_stock(item):
            return self._is_item_in_stock(item, bs)

        return any(map(is_in_stock, items))

    @property
    def watched_item_count(self) -> int:
        return self._item_count or None

    @property
    def name(self) -> str:
        return f"{super().name}[{','.join(self._keywords)}]"


class JsonScanner(Scanner):
    def __init__(self, name, url, method='GET', payload=None, additional_headers=None, **kwargs):
        super().__init__(name)
        self.target_url = url
        self.method = method
        self.payload = payload
        self.headers = {'user-agent': USER_AGENT}
        if additional_headers is not None:
            self.headers.update(additional_headers)
        self.time_out = kwargs.get("time_out", Scanner.DefaultTimeout)

    def _scan_json(self, json: dict) -> bool:
        raise Exception("Not Implemented")

    def _scan(self) -> bool:
        if self.method == 'GET':
            resp = requests.get(self.target_url, headers=self.headers, timeout=self.time_out)
        elif self.method == 'POST':
            resp = requests.post(self.target_url, data=self.payload, headers=self.headers, timeout=self.time_out)
        else:
            raise ValueError("Unsupported HTTP method: " + self.method)
        resp.raise_for_status()
        json = resp.json()
        return self._scan_json(json)


class LDLCScanner(SearchBasedHtmlScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "LDLC"
        super().__init__(name, search_terms, ** kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.ldlc.com/recherche/{quote('+'.join(self._keywords))}/"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".listing-product .pdt-item")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> Tag:
        return item.find(class_="title-3").get_text()

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return len(item.select(".stock-web .stock-1,.stock-web .stock-2")) > 0


class TopAchatScanner(SearchBasedHtmlScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "TopAchat"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.topachat.com/pages/recherche.php?cat=accueil&etou=0&mc={quote('+'.join(self._keywords))}"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select('.produits.list article')

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.find(class_="libelle").get_text()

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return item.find(class_="en-stock") is not None


class HardwareFrScanner(SearchBasedHtmlScanner):
    def __init__(self, search_terms: str, **kwargs):
        name = "HardwareFr"
        super().__init__(name, search_terms, **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://shop.hardware.fr/search/+ftxt-{quote('-'.join(self._keywords))}/"

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select("li[data-ref]")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.find(class_="description").get_text()

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        item_id = item.attrs["id"]
        script_data = ''.join(s.string for s in bs.find_all("script", attrs={"src": None}))
        stock_type = int(re.search("#{id}.*?stock-wrapper.*?stock-([0-9])".format(id=item_id), script_data)[1])
        return stock_type <= 2


class CaseKingScanner(SearchBasedHtmlScanner):
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

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return item.find(class_="deliverable1") is not None


class AlternateScanner(SearchBasedHtmlScanner):
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

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return item.select_one(".stockStatus.available_stock") is not None


class NvidiaScanner(JsonScanner):
    def __init__(self, search_terms: str, *args, **kwargs):
        self._keywords, self._blacklist = parse_search_terms(search_terms)
        super().__init__("Nvidia",
                         "https://api.nvidia.partners/edge/product/search?page=1&limit=100&locale=fr-fr&manufacturer=NVIDIA",
                         *args, **kwargs)

    # @property
    # def target_url(self) -> str:
    #     return "https://api.nvidia.partners/edge/product/search?page=1&limit=100&locale=fr-fr&manufacturer=NVIDIA"

    def _get_all_items_in_json(self, json: dict) -> List[dict]:
        products = list(json["searchedProducts"]["productDetails"])
        products.append(json["searchedProducts"]["featuredProduct"])
        return products

    def _get_item_title(self, item: dict, json: dict) -> str:
        return item["productTitle"]

    def _is_item_in_stock(self, item: dict, json: dict) -> bool:
        return item["prdStatus"] != "out_of_stock"

    def _scan_json(self, json: dict) -> bool:
        keywords = self._keywords
        blacklist = self._blacklist

        def is_wanted(item: dict) -> bool:
            title = self._get_item_title(item, json)
            assert bool(title)
            text = title.lower()
            return all(k in text for k in keywords) and not any(k in text for k in blacklist)

        items = list(filter(is_wanted, self._get_all_items_in_json(json)))
        self._item_count = len(items)
        assert self._item_count > 0

        def is_in_stock(item):
            return self._is_item_in_stock(item, json)

        return any(map(is_in_stock, items))

    @property
    def watched_item_count(self) -> int:
        return self._item_count or None

    @property
    def name(self) -> str:
        return f"{super().name}[{','.join(self._keywords)}]"

    @property
    def user_url(self) -> str:
        return "https://www.nvidia.com/fr-fr/shop/geforce/?page=1&limit=9&locale=fr-fr&manufacturer=NVIDIA"


class RueDuCommerceScanner(JsonScanner):
    def __init__(self, **kwargs):
        super().__init__("RueDuCommerce",
                         "https://www.rueducommerce.fr/listingDyn?urlActuelle=evga-3080&boutique_id=18&langue_id=1"
                         "&recherche=evga-3080&gammesId=25476&from=0", **kwargs)

    def _scan_json(self, json: dict) -> bool:
        def in_stock(product):
            return product["Disponibilite"] == "en stock"

        return any(filter(in_stock, json["produits"]))

    @property
    def user_url(self) -> str:
        return "https://www.rueducommerce.fr/r/evga-3080.html"


class MaterielNetScanner(JsonScanner):
    def __init__(self, **kwargs):
        super().__init__("MaterielNet",
                         "https://www.materiel.net/product-listing/stock-price/",
                         method='POST',
                         payload="json=%7B%22currencyISOCode3%22%3A%22EUR%22%2C%22offers%22%3A%5B%7B%22offerId%22%3A"
                                 "%22AR202009090100%22%2C%22marketplace%22%3Afalse%7D%2C%7B%22offerId%22%3A"
                                 "%22AR202009090101%22%2C%22marketplace%22%3Afalse%7D%2C%7B%22offerId%22%3A"
                                 "%22AR202012070098%22%2C%22marketplace%22%3Afalse%7D%2C%7B%22offerId%22%3A"
                                 "%22AR202009090098%22%2C%22marketplace%22%3Afalse%7D%2C%7B%22offerId%22%3A"
                                 "%22AR202009090099%22%2C%22marketplace%22%3Afalse%7D%2C%7B%22offerId%22%3A"
                                 "%22AR202009100088%22%2C%22marketplace%22%3Afalse%7D%2C%7B%22offerId%22%3A"
                                 "%22AR202012070099%22%2C%22marketplace%22%3Afalse%7D%5D%2C%22shops%22%3A%5B%7B"
                                 "%22shopId%22%3A-1%7D%5D%7D&shopId=-1&displayGroups=Web&shopsAvailability=%7B"
                                 "%22AR202009090100%22%3A%220%22%2C%22AR202009090101%22%3A%220%22%2C%22AR202012070098"
                                 "%22%3A%220%22%2C%22AR202009090098%22%3A%220%22%2C%22AR202009090099%22%3A%220%22%2C"
                                 "%22AR202009100088%22%3A%220%22%2C%22AR202012070099%22%3A%220%22%7D",
                         additional_headers={
                             'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                             'x-requested-with': 'XMLHttpRequest'
                         },
                         **kwargs)

    def _scan_json(self, json: dict) -> bool:
        assert len(json["price"]) > 0

        def is_in_stock(art):
            match = re.search(r"o-availability__value--stock_([0-9])", art)
            assert match
            return int(match[1]) <= 2

        return any(map(is_in_stock, json["stock"].values()))

    @property
    def user_url(self) -> str:
        return "https://www.materiel.net/carte-graphique/l426/+fb-C000033842+fv121-19183/"
