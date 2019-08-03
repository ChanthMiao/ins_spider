# ins_spider

## 这是什么

这是一个基于aiohttp实现的异步Instagram爬虫，可批量爬取公开ins账号的图片帖信息。

## 基本功能

- 按给定公开账户名爬取相关数据。
- 按关键词列表搜索公开账户。
- 3处自定义钩子函数。
- 用户友好的数据交互（提供NamedTunple和dict类型的数据报告）
- 代理（受限于aiohttp，目前仅支持http）

## 爬取信息范围

- 基本用户信息
  - [x] 数字标识
  - [x] 发帖数
  - [x] 关注数
  - [x] 被关注数
  - [x] 个人简介
- 帖子信息
  - [x] 数字标识
  - [x] shortcode
  - [x] 发帖时间
  - [x] 👍点赞数
  - [x] 评论数
  - [x] 图片直链
  - [ ] ~~评论列表~~
  
## 第三方依赖

- aiohttp
- coloredlogs

## 用法

- 基本接口作用已在注释文档提供。
- 要整合本项目仅需将整个spider文件夹拷贝一份至你的项目中，然后执行必要的导入操作。

  ```python
  import asyncio
  import aiohttp
  from spider import core
  '''你的代码'''
  ```

## Demo

本项目为对历史同步爬虫[inspyder](https://github.com/ChanthMiao/inspyder)的简单重构，旨在拥有代理池时实现安全的并发爬取。关于如何利用异步机制实现并发爬取，我提供了一个[demo](./demo_to_json.py)以供参考。

## Q&A

- > 是否支持爬取评论列表？
  - 暂不支持，也未打算支持。但是，当前爬取的帖子数据中有shortcode字段。你可以通过该字段生成帖子详情页的url。

- > 是否有必要使用代理池？
  - 当你并发爬取时，是的。由于本爬虫基于aiohttp这样的异步网络库，即使是在单线程下其并发爬取发起的请求频率也十分惊人。这意味着，如果你不为每个协程中的爬虫分配不同的代理，你将很快因为异常频繁的请求被Instagram拉黑。

- > 为何没有直接移植原项目的数据库相关代码？
  - 原项目[inspyder](https://github.com/ChanthMiao/inspyder)是2天匆忙赶制的玩具，抛开糟糕的编码，网络请求库requests和数据库依赖sqlalchemy均为同步形的库。直接引入会阻塞整个线程，与协程式代码无法优雅的合作（可以另开一个线程给数据库操作，但这会增加代码复杂度）。

- >那么，如何优雅的引入异步数据库操作？
  - 我在项目中提供了3处可自定义的钩子，你可以传入自定义的异步方法。在此推荐一个十分不错的异步的数据库驱动[asyncpg](https://github.com/MagicStack/asyncpg)。
