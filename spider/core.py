import asyncio
import json
import logging
import pprint
import random
import re
from types import FunctionType
from typing import List, Mapping, NamedTuple, Optional

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


async def search(keywords: List[str],
                 proxy: Optional[str] = None) -> List[str]:
    rt = []
    async with aiohttp.ClientSession(headers=default_headers) as clt:
        rank_token = str(random.random())
        for key in keywords:
            search_query = "context=blended&query=\'{0}\'&rank_token=\'{1}\'&include_reel=true".format(
                key, rank_token)
            async with clt.get(instagramIndex + '/web/search/topsearch/?' +
                               search_query,
                               proxy=proxy) as resp:
                search_json = await resp.json()
                userlist = search_json['users']
                for node in userlist:
                    if node['user']['is_private'] is False:
                        rt.append(node['user']['username'])
    return rt


class AccountProfile(NamedTuple):
    id: str = '-1'
    username: str = ''
    posts: int = -1
    following: int = -1
    follower: int = -1
    biography: str = ''


class OnePost(NamedTuple):
    id: str = '-1'
    shortcode: str = ''
    timestamp: int = -1
    stars: int = -1
    comments: int = -1
    url: str = ''
    uid: str = '-1'


class OneUser(NamedTuple):
    user: AccountProfile
    edges: List[OnePost] = []


class Spider(object):
    def __init__(self,
                 username: Optional[str] = None,
                 session: Optional[aiohttp.ClientSession] = None,
                 headers: Optional[Mapping[str, str]] = default_headers,
                 proxy: Optional[str] = None,
                 haslog: bool = True) -> None:
        if haslog is False:
            self.__spi_logger = None
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
        if self.__proxy is not None and self.__spi_logger is not None:
            self.__spi_logger.info(
                'spider for user \'{0}\' sets http(s) proxy \'{1}\''.format(
                    self.__username, self.__proxy))
        self.__patterns = default_pattern
        self.__flags = {'has_next_page': False}
        self.__curr_page: list = []
        self.__profile: AccountProfile = None
        self.__post_list: List[OnePost] = []
        self.__hook1: Optional[FunctionType] = None
        self.__hook2: Optional[FunctionType] = None
        self.__hook3: Optional[FunctionType] = None

    async def _fresh_ua(self,
                        kind: Optional[int] = None,
                        cust_ua_str: Optional[str] = None) -> None:
        if cust_ua_str is not None:
            self.__headers["User-Agent"] = cust_ua_str
        else:
            ua_page = "http://useragentstring.com/pages/useragentstring.php?name={0}"
            param: str
            if kind is None or kind == 0:
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

    async def fake_headers(self,
                           headers: Optional[dict] = None,
                           ua_code: Optional[int] = None,
                           cust_ua: Optional[str] = None) -> None:
        if headers is not None:
            for k, v in headers.items:
                self.__headers[k] = v
        if self.__headers.get("User-Agent") is None:
            await self._fresh_ua(kind=ua_code, cust_ua_str=cust_ua)
        if self.__spi_logger is not None:
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
        current_page_posts = []
        for node in self.__curr_page:
            if node["node"]["is_video"] is False:
                tmp = OnePost(node["node"]["id"], node["node"]["shortcode"],
                              node["node"]["taken_at_timestamp"],
                              node["node"]["edge_media_preview_like"]["count"],
                              node["node"]["edge_media_to_comment"]["count"],
                              node["node"]["display_url"], self.__profile.id)
                current_page_posts.append(tmp)
                if self.__spi_logger is not None:
                    self.__spi_logger.info(
                        'new posts record of user \'{0}\' loaded:\n{1}'.format(
                            self.__username, tmp))
            elif self.__spi_logger is not None:
                self.__spi_logger.info("post {0} is video, skip it".format(
                    node["node"]["id"]))
        self.__post_list.extend(current_page_posts)
        if self.__hook2 is not None:
            self.__hook2(current_page_posts, self)

    async def load_user_index(self) -> int:
        async with self.__session.get(
                instagramIndex + "/" + self.__username,
                proxy=self.__proxy,
                headers=self.__headers) as user_index_resp:
            if user_index_resp.status == 404:
                await user_index_resp.text()
                if self.__spi_logger is not None:
                    self.__spi_logger.warning(
                        'user \'{0} does not exist.\''.format(self.__username))
                return 404
            user_index = await user_index_resp.text()
            await self._load_js_flags(user_index)
            sharedData = self.__patterns["shardData"].search(
                user_index).groups()[0]
            config = json.loads(sharedData, encoding='utf-8')
            is_private: bool = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["is_private"]
            if is_private:
                if self.__spi_logger is not None:
                    self.__spi_logger.warning(
                        'user \'{0} is private.\''.format(self.__username))
                return 503
            self.__profile = AccountProfile(
                config["entry_data"]["ProfilePage"][0]["graphql"]["user"]
                ["id"], self.__username, config["entry_data"]["ProfilePage"][0]
                ["graphql"]["user"]["edge_owner_to_timeline_media"]["count"],
                config["entry_data"]["ProfilePage"][0]["graphql"]["user"]
                ["edge_follow"]["count"], config["entry_data"]["ProfilePage"]
                [0]["graphql"]["user"]["edge_followed_by"]["count"],
                config["entry_data"]["ProfilePage"][0]["graphql"]["user"]
                ["biography"])
            self.__flags['has_next_page'] = config["entry_data"][
                "ProfilePage"][0]["graphql"]["user"][
                    "edge_owner_to_timeline_media"]["page_info"][
                        "has_next_page"]
            self.__flags['end_curr'] = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["edge_owner_to_timeline_media"][
                    "page_info"]["end_cursor"]
            self.__curr_page = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["edge_owner_to_timeline_media"]["edges"]
            if self.__spi_logger is not None:
                self.__spi_logger.info('new user profile loaded:\n{}'.format(
                    self.__profile))
            if self.__hook1 is not None:
                self.__hook1(self.__profile, self)
            self.load_current_posts()
            return 200

    async def _next_page(self) -> None:
        self.merge_headers({'X_Request_With': "XMLHttpRequest"})
        query_url = instagramIndex + '/graphql/query/?query_hash={0}&variables={{"id":"{1}","first":12,"after":"{2}"}}'.format(
            self.__flags['queryId'], self.__profile.id,
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
            if self.__spi_logger is not None:
                self.__spi_logger.info(
                    'user \'{0}\' switched to the next page.'.format(
                        self.__username))

    async def next_page(self) -> None:
        if self.__flags['has_next_page'] is True:
            await self._next_page()
            self.pop_headers(['X_Request_With'])
        elif self.__spi_logger is not None:
            self.__spi_logger.warning(
                'user \'{0}\', no next page available!'.format(
                    self.__username))

    async def all_pages(self) -> None:
        while self.__flags['has_next_page'] is True:
            await asyncio.sleep(random.random() * 5)
            await self._next_page()
        self.pop_headers(['X_Request_With'])
        if self.__spi_logger is not None:
            self.__spi_logger.info(
                'No next page available, all posts of user \'{0}\' loaded!'.
                format(self.__username))
        if self.__hook3 is not None:
            self.__hook3(self.__profile, self.__post_list, self)

    def get_report(self) -> OneUser:
        return OneUser(self.__profile, self.__post_list)

    async def run(self,
                  ua_code: Optional[int] = None,
                  cust_ua_str: Optional[str] = None) -> None:
        await self.fake_headers(ua_code=ua_code, cust_ua=cust_ua_str)
        rt_code = await self.load_user_index()
        if rt_code == 200:
            await self.all_pages()

    def get_progress(self) -> float:
        return len(self.__post_list) / self.__profile.posts

    def json(self) -> dict:
        def post_to_dict(p: OnePost):
            tmp = dict(p._asdict())
            tmp.pop('uid')
            return tmp

        data = {'profile': None, 'edges': []}
        data['profile'] = dict(self.__profile._asdict())
        for post in map(post_to_dict, self.__post_list):
            data['edges'].append(post)
        return data

    def set_hooks(self,
                  after_profile: Optional[FunctionType] = None,
                  after_one_page: Optional[FunctionType] = None,
                  after_all: Optional[FunctionType] = None) -> None:
        self.__hook1 = after_profile
        self.__hook2 = after_one_page
        self.__hook3 = after_all
