import asyncio
import json
import logging
import random
import re
from types import FunctionType
from typing import List, Mapping, NamedTuple, Optional, Type

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
cacahed_flags = {}


async def search(keywords: List[str],
                 proxy: Optional[str] = None) -> List[str]:
    '''
    按给定关键字列表搜索可用的公开账户。
    '''
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
                 username: Type[str],
                 session: Type[aiohttp.ClientSession],
                 headers: Optional[Mapping[str, str]] = default_headers,
                 proxy: Optional[str] = None,
                 haslog: bool = True) -> None:
        '''
        构建一个爬虫实例。请至少提供账户名和ClientSession实例。
        '''
        if haslog is False:
            self.__spi_logger = None
        else:
            self.__spi_logger = logging.getLogger('spider')
        coloredlogs.install(level='INFO',
                            logger=self.__spi_logger,
                            fmt="[%(levelname)s] %(asctime)s  %(message)s")
        if username is None:
            raise RuntimeError('username can not be None')
        self.username = username
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
                    self.username, self.__proxy))
        self.__patterns = default_pattern
        self.__flags = {'has_next_page': False, 'loaded': -1}
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
                    self.username, self.__headers))

    async def _load_js_flags(self, userIndex: str) -> None:
        if cacahed_flags.get('X_IG_APP_ID') is not None:
            self.__flags['X_IG_APP_ID'] = cacahed_flags['X_IG_APP_ID']
        else:
            clc_js_uri = self.__patterns['clc_js'].search(userIndex).group()
            async with self.__session.get(
                    instagramIndex + clc_js_uri,
                    proxy=self.__proxy,
                    headers=self.__headers) as clc_js_resp:
                clc_js = await clc_js_resp.text()
                self.__flags['X_IG_APP_ID'] = self.__patterns[
                    'X_IG_APP_ID'].search(clc_js).groups()[0]
            cacahed_flags['X_IG_APP_ID'] = self.__flags['X_IG_APP_ID']
        if cacahed_flags.get('queryId') is not None:
            self.__flags['queryId'] = cacahed_flags['queryId']
        else:
            ppc_js_uri = self.__patterns['ppc_js'].search(userIndex).group()
            async with self.__session.get(
                    instagramIndex + ppc_js_uri,
                    proxy=self.__proxy,
                    headers=self.__headers) as ppc_js_resp:
                ppc_js = await ppc_js_resp.text()
                self.__flags['queryId'] = self.__patterns['queryId'].search(
                    ppc_js).groups()[0]
            cacahed_flags['queryId'] = self.__flags['queryId']

    def get_headers(self) -> Optional[Mapping[str, str]]:
        return self.__headers

    def merge_headers(self,
                      additional_headers: Optional[Mapping[str, str]]) -> None:
        for k, v in additional_headers.items():
            self.__headers[k] = v

    def pop_headers(self, keys: List[str]) -> None:
        for key in keys:
            if self.__headers.get(key) is not None:
                self.__headers.pop(key)

    async def _load_current_posts(self):
        '''
        加载当前页面的所有图片帖信息至已爬取帖子列表。\n
        支持在加载完成后执行账户自定义钩子函数。\n
        警告：不建议显示调用
        '''
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
                            self.username, tmp))
            elif self.__spi_logger is not None:
                self.__spi_logger.info("post {0} is video, skip it".format(
                    node["node"]["id"]))
            self.__flags['loaded'] += 1
        self.__post_list.extend(current_page_posts)
        if self.__hook2 is not None:
            await self.__hook2(current_page_posts, self)

    async def load_user_index(self) -> int:
        '''
        加载账户基本信息，并为爬取帖子做好准备（挂载代采集的当前页面数据）。\n
        支持在成功加载后执行账户自定义钩子函数。\n
        返回值：404-账户不存在；503-账户不可见；200-成功。
        '''
        async with self.__session.get(
                instagramIndex + "/" + self.username,
                proxy=self.__proxy,
                headers=self.__headers) as user_index_resp:
            if user_index_resp.status == 404:
                await user_index_resp.text()
                if self.__spi_logger is not None:
                    self.__spi_logger.warning(
                        'user \'{0} does not exist.\''.format(self.username))
                return 404
            user_index = await user_index_resp.text()
            if self.__flags.get('X_IG_APP_ID') is None or self.__flags.get(
                    'queryId') is None:
                await self._load_js_flags(user_index)
            sharedData = self.__patterns["shardData"].search(
                user_index).groups()[0]
            config = json.loads(sharedData, encoding='utf-8')
            is_private: bool = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["is_private"]
            if is_private:
                if self.__spi_logger is not None:
                    self.__spi_logger.warning(
                        'user \'{0} is private.\''.format(self.username))
                return 503
            self.__profile = AccountProfile(
                config["entry_data"]["ProfilePage"][0]["graphql"]["user"]
                ["id"], self.username, config["entry_data"]["ProfilePage"][0]
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
            self.__flags['loaded'] = 0
            self.__curr_page = config["entry_data"]["ProfilePage"][0][
                "graphql"]["user"]["edge_owner_to_timeline_media"]["edges"]
            if self.__spi_logger is not None:
                self.__spi_logger.info('new user profile loaded:\n{}'.format(
                    self.__profile))
            if self.__hook1 is not None:
                await self.__hook1(self.__profile, self)
            await self._load_current_posts()
            return 200

    async def _next_page(self) -> None:
        '''
        翻页（instagram网页采用了惰性加载），挂载下一页帖子数据。\n
        内部方法，不建议显示调用，且不应当在load_user_index前被调用。
        '''
        self.merge_headers({'X_Request_With': "XMLHttpRequest"})
        query_url = instagramIndex + '/graphql/query/?query_hash={0}&variables={{"id":"{1}","first":12,"after":"{2}"}}'.format(
            self.__flags['queryId'], self.__profile.id,
            self.__flags['end_curr'])
        async with self.__session.get(
                query_url, proxy=self.__proxy,
                headers=self.__headers) as next_page_resp:
            next_page_json = await next_page_resp.json()
            if next_page_json['status'] == 'ok':
                self.__flags['has_next_page'] = next_page_json['data']['user'][
                    "edge_owner_to_timeline_media"]["page_info"][
                        "has_next_page"]
                self.__flags['end_curr'] = next_page_json["data"]["user"][
                    "edge_owner_to_timeline_media"]["page_info"]["end_cursor"]
                self.__curr_page = next_page_json["data"]["user"][
                    "edge_owner_to_timeline_media"]["edges"]
                await self._load_current_posts()
                if self.__spi_logger is not None:
                    self.__spi_logger.info(
                        'user \'{0}\' switched to the next page.'.format(
                            self.username))
            else:
                if self.__spi_logger is not None:
                    sleeptime = random.randint(10, 16)
                    self.__spi_logger.warning(
                        'user \'{0}\' failed to load current page, try again {1} secs later.'
                        .format(self.username, sleeptime))
                    await asyncio.sleep(sleeptime)

    async def next_page(self) -> None:
        '''
        爬取下一页帖子信息，不应当在load_user_index之前被调用。\n
        由于此方法调用了_load_current_posts，故支持执行钩子函数。
        '''
        if self.__flags['has_next_page'] is True:
            await self._next_page()
            self.pop_headers(['X_Request_With'])
        elif self.__spi_logger is not None:
            self.__spi_logger.warning(
                'user \'{0}\', no next page available!'.format(self.username))

    async def all_pages(self) -> None:
        '''
        爬取账户所有图片贴信息，不应当在load_user_index之前被调用。\n
        支持执行账户自定义钩子函数。
        '''
        while self.__flags['has_next_page'] is True:
            await asyncio.sleep(random.random() * 9)
            await self._next_page()
        self.pop_headers(['X_Request_With'])
        if self.__spi_logger is not None:
            self.__spi_logger.info(
                'No next page available, all posts of user \'{0}\' loaded!'.
                format(self.username))
        if self.__hook3 is not None:
            await self.__hook3(self.__profile, self.__post_list, self)

    def get_report(self) -> OneUser:
        '''
        获取当前目标账户的数据报告，OneUser类型。
        '''
        return OneUser(self.__profile, self.__post_list)

    async def run(self,
                  ua_code: Optional[int] = None,
                  cust_ua_str: Optional[str] = None) -> None:
        '''
        自动爬取给定账户的所有信息。
        '''
        await self.fake_headers(ua_code=ua_code, cust_ua=cust_ua_str)
        rt_code = await self.load_user_index()
        if rt_code == 200:
            await self.all_pages()

    def get_progress(self) -> float:
        '''
        获取当前账户爬取进度。
        '''
        return self.__flags['loaded'] / self.__profile.posts

    def json(self) -> dict:
        '''
        以json格式（实际为dict）输出当前用户完整数据。
        '''

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
        '''
        设置自定义钩子函数，3处执行位置可选。\n
        钩子返回值无意义，建议返回None。\n
        after_profile接收2个参数：AccountProfile类型的用户基本信息和指向实例的指针；\n
        after_one_page接收2个参数：List[OnePost]类型当前页面帖子信息和指向实例的指针；\n
        after_all接收3个参数：AccountProfile类型的用户基本信息、List[OnePost]类型当前页面帖子信息和指向实例的指针。\n
        '''
        self.__hook1 = after_profile
        self.__hook2 = after_one_page
        self.__hook3 = after_all
