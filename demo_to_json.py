import asyncio
import json
import logging
import signal

from typing import List, Optional

import aiohttp
import uvloop

from spider import core
from spider.core import OnePost


def keyboardInterrupHandler(signalk, frame):
    # 处理键盘中断信号。
    logging.getLogger('spider').critical(
        'KeyboardInterrup (ID {0}) has been caught. Exit now.'.format(signalk))
    exit(0)


def progressBar(p: OnePost, ptr: core.Spider):
    # 作为钩子函数传入，提供针对当前用户的爬取进度显示。
    print('progress of current target %s %.2f%%' %
          (ptr.username, ptr.get_progress() * 100))


async def oneWorker(user: str,
                    session: Optional[aiohttp.ClientSession],
                    proxy: str = None) -> None:
    sample = core.Spider(username=user, session=session, proxy=proxy)
    # 设置钩子，触发条件为翻页。
    sample.set_hooks(after_one_page=progressBar)
    # 提供自定义UA。
    await sample.run(cust_ua_str="Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
            AppleWebKit/537.36 (KHTML, like Gecko) \
            Chrome/70.0.3538.77 Safari/537.36")
    # 将数据写入按用户名命名的json文件。
    with open("data/" + sample.username + '.json', "w") as fp:
        json.dump(sample.json(), fp)


async def multiTargetLiner(users: List[str], proxy: str = None) -> None:
    # 复用同一个session线性处理多个目标。
    async with aiohttp.ClientSession() as clt:
        for user in users:
            await oneWorker(user, clt, proxy)


async def run():
    # 按主题获取用户列表。
    users: List[str] = await core.search(['security'],
                                         "http://192.168.139.129:8080")
    jobs = [[], []]
    total = len(users)
    if total == 0:
        print('No target available!')
    elif total <= 2:
        jobs.extend(users)
    else:
        # 分配任务。
        for sub in range(total):
            jobs[sub % 2].append(users[sub])
    works = []
    proxies = ["http://192.168.139.129:8080", "http://192.168.139.129:8080"]
    for i in range(len(jobs)):
        # 理想情况下应为每个multiTargetLiner分配不同的代理，避免同一IP的异常高频请求。
        works.append(multiTargetLiner(jobs[i], proxies[i % 2]))
    await asyncio.gather(*works)


signal.signal(signal.SIGINT, keyboardInterrupHandler)
uvloop.install()
loop = asyncio.get_event_loop()
loop.run_until_complete(run())
loop.run_until_complete(asyncio.sleep(0.250))
loop.close()
