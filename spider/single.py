import asyncio
import json
import logging
import pprint
import random
import re
from typing import List, Mapping, Optional, Type

import aiohttp
import coloredlogs

default_pattern = {
    'clc_js':
    re.compile(r'/static/bundles/es6/ConsumerLibCommons\.js/.*?\.js'),
    'X_IG_APP_ID': re.compile(r"instagramWebDesktopFBAppId='(.*?)'"),
    'ppc_js':
    re.compile(r'/static/bundles/es6/ProfilePageContainer\.js/.*?\.js'),
    'queryId': re.compile(r'l.pagination},queryId:"(.*?)"'),
    'shardData': re.compile(r'window\._sharedData\s*=\s*(.*?);</script>')
}
instagramIndex = "https://www.instagram.com"
default_headers = {
    "cache-Control": "no-cache",
    "Accept-Language": "en-US,en;q=0.8"
}


class single(object):
    def __init__(self,
                 username: Optional[str] = None,
                 session: Optional[aiohttp.ClientSession] = None,
                 headers: Optional[Mapping[str, str]] = default_headers,
                 proxy: Optional[str] = None,
                 spi_logger: Type[logging.Logger] = None) -> None:
        if spi_logger is not None:
            self.__spi_logger = spi_logger
        else:
            self.__spi_logger = logging.getLogger('spider')
        coloredlogs.install(level='INFO',
                            logger=self.__spi_logger,
                            fmt="[%(levelname)s] %(asctime)s  %(message)s")
        if username is None:
            raise RuntimeError('username can not be None')
        self.__username = username
        if session is None:
            raise RuntimeError("session can not be None")
        self.__session = session
        if headers is not None:
            self.__headers = headers
        else:
            self.__headers = {}
        self.__proxy = proxy
        if self.__proxy is not None:
            self.__spi_logger.info(
                'spider for user \'{0}\' sets http(s) proxy \'{1}\''.format(
                    self.__username, self.__proxy))
        self.__patterns = default_pattern
        self.__flags = {'has_next_page': False}
        self.__curr_page: list = []
        self.__data: dict = {'edges': []}

    async def _fresh_ua(self, kind: int = 0) -> None:
        ua_page = "http://useragentstring.com/pages/useragentstring.php?name={}"
        param: str
        if kind == 0:
            param = "Chrome"
        elif kind == 1:
            param = "Firefox"
        elif kind == 2:
            param = "Edge"
        else:
            param = "Chrome"
        async with self.__session.get(ua_page.format(param),
                                      proxy=self.__proxy) as resp:
            body = await resp.text()
            pat_block = r'<h4>(.*?)</h4>(.*?)</li>'
            pat = r"<a\s+href\s*\=\s*'/index\.php\?id=\d+'.*?>(.*?)</a>"
            ua_block = re.search(pat_block, body).groups()
            ua_list = re.findall(pat, ua_block[1])
            if self.__headers is None:
                self.__headers = {}
            self.__headers["User-Agent"] = ua_list[0]

    async def fake_headers(self, headers: dict = None,
                           ua_code: int = 0) -> None:
        if headers is not None:
            for k, v in headers.items:
                self.__headers[k] = v
        if self.__headers.get("User-Agent") is None:
            await self._fresh_ua(ua_code)
        self.__spi_logger.info(
            'spider for user \'{0}\' updates http headers\n\'{1}\''.format(
                self.__username, pprint.pformat(self.__headers)))

    async def _load_js_flags(self, userIndex: str) -> None:
        clc_js_uri = self.__patterns['clc_js'].search(userIndex).group()
        async with self.__session.get(instagramIndex + clc_js_uri,
                                      proxy=self.__proxy,
                                      headers=self.__headers) as clc_js_resp:
            clc_js = await clc_js_resp.text()
            self.__flags['X_IG_APP_ID'] = self.__patterns[
                'X_IG_APP_ID'].search(clc_js).groups()[0]
        ppc_js_uri = self.__patterns['ppc_js'].search(userIndex).group()
        async with self.__session.get(instagramIndex + ppc_js_uri,
                                      proxy=self.__proxy,
                                      headers=self.__headers) as ppc_js_resp:
            ppc_js = await ppc_js_resp.text()
            self.__flags['queryId'] = self.__patterns['queryId'].search(
                ppc_js).groups()[0]

    def get_headers(self) -> Optional[Mapping[str, str]]:
        return self.__headers

    def merge_headers(self,
                      additional_headers: Optional[Mapping[str, str]]) -> None:
        for k, v in additional_headers.items():
            self.__headers[k] = v

    def pop_headers(self, keys: List[str]) -> None:
        for key in keys:
            self.__headers.pop(key)

    def load_current_posts(self):
        for node in self.__curr_page:
            # TODO output
            pic_id = node["node"]["id"]
            pic_time_stamp = node["node"]["taken_at_timestamp"]
            pic_stars = node["node"]["edge_media_preview_like"]["count"]
            pic_comments = node["node"]["edge_media_to_comment"]["count"]
            pic_url = node["node"]["display_url"]
            new_record = {
                'id': pic_id,
                'time_stamp': pic_time_stamp,
                'stars': pic_stars,
                'comments': pic_comments,
                'url': pic_url
            }
            self.__data['edges'].append(new_record)
            readable_record = pprint.pformat(new_record)
            self.__spi_logger.info(
                'new posts record of user \'{0}\' loaded:\n{1}'.format(
                    self.__username, readable_record))

    async def load_user_index(self) -> int:
        async with self.__session.get(
                instagramIndex + "/" + self.__username,
                proxy=self.__proxy,
                headers=self.__headers) as user_index_resp:
            if user_index_resp.status == 404:
                await user_index_resp.text()
                self.__spi_logger.error('user \'{0} does not exist.\''.format(
                    self.__username))
                return 404
            user_index = await user_index_resp.text()
            await self._load_js_flags(user_index)
            sharedData = self.__patterns["shardData"].search(
                user_index).groups()[0]
            config = json.loads(sharedData, encoding='utf-8')
            self.__data['id'] = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["id"]
            self.__data['posts'] = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["edge_owner_to_timeline_media"]["count"]
            self.__data['following'] = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["edge_follow"]["count"]
            self.__data['followers'] = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["edge_followed_by"]["count"]
            self.__data['biography'] = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["biography"]
            self.__flags['has_next_page'] = config["entry_data"][
                "ProfilePage"][0]["graphql"]["user"][
                    "edge_owner_to_timeline_media"]["page_info"][
                        "has_next_page"]
            self.__flags['end_curr'] = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["edge_owner_to_timeline_media"][
                    "page_info"]["end_cursor"]
            self.__curr_page = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["edge_owner_to_timeline_media"]["edges"]
            readable_record = pprint.pformat(self.__data)
            self.__spi_logger.info(
                'new user profile loaded:\n{}'.format(readable_record))
            self.load_current_posts()
            return 200

    async def _next_page(self) -> None:
        self.merge_headers({'X_Request_With': "XMLHttpRequest"})
        query_url = instagramIndex + '/graphql/query/?query_hash={0}&variables={{"id":"{1}","first":12,"after":"{2}"}}'.format(
            self.__flags['queryId'], self.__data['id'],
            self.__flags['end_curr'])
        async with self.__session.get(
                query_url, proxy=self.__proxy,
                headers=self.__headers) as next_page_resp:
            next_page_json = await next_page_resp.json()
            self.__flags['has_next_page'] = next_page_json['data']['user'][
                "edge_owner_to_timeline_media"]["page_info"]["has_next_page"]
            self.__flags['end_curr'] = next_page_json["data"]["user"][
                "edge_owner_to_timeline_media"]["page_info"]["end_cursor"]
            self.__curr_page = next_page_json["data"]["user"][
                "edge_owner_to_timeline_media"]["edges"]
            self.load_current_posts()
            self.__spi_logger.info(
                'user \'{0}\' switched to the next page.'.format(
                    self.__username))

    async def next_page(self) -> None:
        if self.__flags['has_next_page'] is True:
            await self._next_page()
            self.pop_headers(['X_Request_With'])
        else:
            self.__spi_logger.warning(
                'user \'{0}\', no next page available!'.format(
                    self.__username))

    async def all_pages(self) -> None:
        while self.__flags['has_next_page'] is True:
            await asyncio.sleep(random.random() * 3)
            await self._next_page()
        self.pop_headers(['X_Request_With'])
        self.__spi_logger.info(
            'No next page available, all posts of user \'{0}\' loaded!'.format(
                self.__username))

    def get_report(self) -> dict:
        return self.__data

    async def run(self) -> None:
        await self.fake_headers()
        rt_code = await self.load_user_index()
        if rt_code == 200:
            await self.all_pages()
