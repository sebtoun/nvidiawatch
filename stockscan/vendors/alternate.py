from stockscan.scanner import SearchBasedHttpScanner, make_soup
from typing import List
from urllib.parse import quote
from bs4 import BeautifulSoup
from bs4.element import Tag
from yarl import URL

from aiohttp import ClientTimeout
import aiohttp


class AlternateScanner(SearchBasedHttpScanner, is_concrete_scanner=False):
    def __init__(self, search_terms: str, locale: str, **kwargs):
        name = "Alternate" + locale.upper()
        self._locale = locale.lower()
        super().__init__(name, search_terms, method="POST", **kwargs)

    @property
    def target_url(self) -> str:
        return f"https://www.alternate.{self._locale}/listing.xhtml"

    @property
    def payload(self) -> dict:
        return {'lazyForm': 'lazyForm',
                'q': ' '.join(self._keywords),
                'lazyComponent': 'lazyListingContainer',
                'javax.faces.ViewState': 'stateless',
                'javax.faces.source': 'lazyButton',
                'javax.faces.partial.event': 'click',
                'javax.faces.partial.execute': 'lazyButton lazyButton',
                'javax.faces.behavior.event': 'action',
                'javax.faces.partial.ajax': 'true'}

    async def _scan(self):
        async with aiohttp.ClientSession(headers=self.request_headers,
                                         raise_for_status=True,
                                         timeout=ClientTimeout(total=self.time_out)) as session:

            query_url = f'{self.target_url}?q={quote(" ".join(self._keywords))}'
            async with session.get(query_url):
                # get session cookies
                pass

            headers = {
                'Origin': f'https://www.alternate.{self._locale}',
                'Referer': query_url
            }
            async with session.post(self.target_url, data=self.payload, headers=headers) as resp:
                text = await resp.text()
                content = make_soup(text)
                self.request_url = resp.url
                return await self._scan_response(content)

    def _get_all_items_in_page(self, bs: BeautifulSoup) -> List[Tag]:
        return bs.select(".listing a.productBox")

    def _get_item_title(self, item: Tag, bs: BeautifulSoup) -> str:
        return item.select_one("div.product-name").get_text().strip()

    def _get_item_price(self, item: Tag, content: BeautifulSoup) -> float:
        def parse_price(text: str) -> float:
            return float(text.replace('€', '').replace('.', '').replace(',', '.').strip())

        return parse_price(item.select_one(".price").get_text())

    def _is_item_in_stock(self, item: Tag, bs: BeautifulSoup) -> bool:
        return item.select_one(".delivery-info").get_text().strip().lower() == "en stock"

    def _get_item_url(self, item: Tag, content: BeautifulSoup) -> str:
        return item.attrs["href"]

    @property
    def user_url(self) -> str:
        return f'https://www.alternate.{self._locale}/listing.xhtml?q={quote(" ".join(self._keywords))}'


class AlternateDEScanner(AlternateScanner):
    def __init__(self, search_terms: str, **kwargs):
        super().__init__(search_terms, locale='de', **kwargs)


class AlternateFRScanner(AlternateScanner):
    def __init__(self, search_terms: str, **kwargs):
        super().__init__(search_terms, locale='fr', **kwargs)
