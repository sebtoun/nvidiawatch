import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import time
import random
from typing import Dict, Union


def make_soup(resp: requests.Response):
    return BeautifulSoup(resp.content, 'html.parser')


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
        raise NotImplemented

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
        raise NotImplemented

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
    def __init__(self, name, url, **kwargs):
        super().__init__(name)
        self.target_url = url
        self.headers = {'user-agent': USER_AGENT}
        self.time_out = kwargs.get("time_out", Scanner.DefaultTimeout)

    def _scan_html(self, bs: BeautifulSoup) -> bool:
        raise NotImplemented

    def _scan(self) -> bool:
        resp = requests.get(self.target_url, headers=self.headers, timeout=self.time_out)
        resp.raise_for_status()
        bs = make_soup(resp)
        return self._scan_html(bs)

    @property
    def user_url(self) -> str:
        return self.target_url


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
        raise NotImplemented

    def _scan(self) -> bool:
        if self.method == 'GET':
            resp = requests.get(self.target_url, headers=self.headers, timeout=self.time_out)
        elif self.method == 'POST':
            resp = requests.post(self.target_url, data=self.payload, headers=self.headers, timeout=self.time_out)
        else:
            raise ValueError("Unsopported HTTP method: " + self.method)
        resp.raise_for_status()
        json = resp.json()
        return self._scan_json(json)


class LDLCScanner(HtmlScanner):
    def __init__(self, *args, **kwargs):
        super().__init__("LDLC", "https://www.ldlc.com/recherche/evga%203080/",
                         *args, **kwargs)

    def _scan_html(self, bs: BeautifulSoup) -> bool:
        assert len(bs.select(".stock-web")) > 0
        total = len(bs.select('.stock-web .stock-1')) + len(bs.select('.stock-web .stock-2'))
        return total > 0


class TopAchatScanner(HtmlScanner):
    def __init__(self, *args, **kwargs):
        super().__init__("TopAchat", "https://www.topachat.com/pages"
                                     "/produits_cat_est_micro_puis_rubrique_est_wgfx_pcie_puis_mc_est_evga%252B3080.html",
                         *args, **kwargs)

    def _scan_html(self, bs: BeautifulSoup) -> bool:
        assert len(bs.select('.produits.list article')) > 0
        return len(bs.select('.en-stock')) > 0


class HardwareFrScanner(HtmlScanner):
    def __init__(self, *args, **kwargs):
        super().__init__("HardwareFr", "https://shop.hardware.fr/search/+ftxt-evga-3080+fcat-7492/",
                         *args, **kwargs)

    def _scan_html(self, bs: BeautifulSoup) -> bool:
        script = bs.find_all("script")[9].string
        found = re.findall(r"\.stock-wrapper.*?stock-([0-9])", script)
        assert len(found) > 0
        return any(filter(lambda n: int(n) <= 2, found))


class CaseKingScanner(HtmlScanner):
    def __init__(self, *args, **kwargs):
        super().__init__("CaseKing",
                         "https://www.caseking.de/en/search/index/sSearch/evga+3080/sPerPage/48/sFilter_supplier/EVGA",
                         *args, **kwargs)

    def _scan_html(self, bs: BeautifulSoup) -> bool:
        def is_3080(art):
            return "3080" in art.find(class_="producttitles").attrs["data-description"]

        def is_in_stock(art):
            return art.find(class_="deliverable1") is not None

        articles = list(filter(is_3080, bs.select(".artbox")))
        assert len(articles) > 0
        return any(map(is_in_stock, articles))


class AlternateScanner(HtmlScanner):
    def __init__(self, *args, **kwargs):
        super().__init__("Alternate",
                         "https://www.alternate.de/html/search.html?query=evga+3080&filter_-1=15500&filter_-1=111900"
                         "&filter_416=170",
                         *args, **kwargs)

    def _scan_html(self, bs: BeautifulSoup) -> bool:
        assert len(bs.select(".stockStatus")) > 0
        return len(bs.select(".stockStatus.available_stock")) > 0


class NvidiaScanner(JsonScanner):
    def __init__(self, *args, **kwargs):
        super().__init__("Nvidia",
                         "https://api.nvidia.partners/edge/product/search?page=1&limit=9&locale=fr-fr&category=GPU"
                         "&gpu=RTX%203080,RTX%203090&manufacturer=NVIDIA&manufacturer_filter=NVIDIA~2,ASUS~8,EVGA~5,"
                         "GAINWARD~2,GIGABYTE~5,MSI~4,PNY~4,ZOTAC~3",
                         *args, **kwargs)

    def _scan_json(self, json: dict) -> bool:
        products = list(json["searchedProducts"]["productDetails"])
        products.append(json["searchedProducts"]["featuredProduct"])

        def validate(product):
            return product["productSKU"] in ["NVGFT080", "NVGFT090"]

        def is_in_stock(product):
            return product["prdStatus"] != "out_of_stock"

        assert all(map(validate, products))
        return any(map(is_in_stock, products))

    @property
    def user_url(self) -> str:
        return "https://www.nvidia.com/fr-fr/shop/geforce/?page=1&limit=9&locale=fr-fr"


class RueDuCommerceScanner(JsonScanner):
    def __init__(self, *args, **kwargs):
        super().__init__("RueDuCommerce",
                         "https://www.rueducommerce.fr/listingDyn?urlActuelle=evga-3080&boutique_id=18&langue_id=1"
                         "&recherche=evga-3080&gammesId=25476&from=0",
                         *args, **kwargs)

    def _scan_json(self, json: dict) -> bool:
        def in_stock(product):
            return product["Disponibilite"] == "en stock"

        return any(filter(in_stock, json["produits"]))

    @property
    def user_url(self) -> str:
        return "https://www.rueducommerce.fr/r/evga-3080.html"


class MaterielNetScanner(JsonScanner):
    def __init__(self, *args, **kwargs):
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
                         *args, **kwargs)

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
