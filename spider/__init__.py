# 基于异步io的免登录instagram爬虫。
# 作者 Chanth Miao
"""
本模块基于异步http库:mod:`aiohttp`实现了针对Instagram图片帖的自动爬虫。

按给定用户名爬取（无意义，仅作示范）。
======
>>> import asyncio
>>> import aiohttp
>>> import uvloop
>>> import json
>>> from spider import single
>>> # 定义一个异步方法。
>>> async def run(username: str, proxy: str=None):
>>>         async with aiohttp.ClientSession() as session:
>>>             sample = single.single(username=username,
>>>                                    session=session,
>>>                                    proxy=proxy)
>>>             await sample.run()
>>>             with open('report.json', "w") as fp:
>>>                 json.dump(sample.get_report(), fp) # 自行处理的到的数据。此处导出json文件。
>>> # 注册loop。
>>> uvloop.install()
>>> loop = asyncio.get_event_loop()
>>> loop.run_until_complete(run('instagram'))
>>> # 等待底层连接完全关闭。
>>> loop.run_until_complete(asyncio.sleep(0.250))
>>> loop.close()

并发执行，利用协程优势
====================
>>> #定义一个并发调用。
>>> async def wrap_run():
>>>     #条件允许的情况下，我建议为每一个`single`实例提供不同的代理。
>>>     await asyncio.gather(run('instagram', 'http://localhost:8080'), run('test', 'http://localhost:8081'))
>>> # 注册loop
>>> uvloop.install()
>>> loop = asyncio.get_event_loop()
>>> loop.run_until_complete(wrap_run())
>>> # 等待底层连接完全关闭。
>>> loop.run_until_complete(asyncio.sleep(0.250))
>>> loop.close()
"""
__version__ = '1.0.0'
