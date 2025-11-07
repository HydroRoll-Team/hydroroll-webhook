.. |Done| image:: https://img.shields.io/badge/Done-100%25-green
.. |python_v| image:: https://img.shields.io/badge/Python-3.9+-blue?style=flat&logo=python
   :target: https://www.python.org/
.. |iamai_v| image:: https://img.shields.io/badge/iamai-0.0.2-green?style=flat
   :target: https://iamai.is-a.dev/
.. |license| image:: https://img.shields.io/badge/License-MIT-yellow?style=flat
   :target: https://github.com/HydroRoll-Team/hydroroll-webhook/blob/main/LICENSE
.. |docker| image:: https://img.shields.io/badge/Docker-Supported-blue?style=flat&logo=docker
   :target: https://www.docker.com/
.. |community| image:: https://img.shields.io/badge/加入社区-002fa7.svg?style=flat-square
   :target: https://github.com/HydroRoll-Team/support/issues/new/choose
   :alt: 加入社区


HydroRoll Webhook |logo| 
========================

|python_v| |iamai_v| |license| |docker| |community|

----

    [!NOTE]

    该项目不会频繁更新!

----


.. list-table::
    :widths: 15 25 60
    :header-rows: 1
    :align: center

    * - 模块
      - 状态
      - 说明
    * - Webhook 插件
      - |Done|
      - GitHub Webhook 事件接收与转发
    * - ArxivRSS 插件
      - |Done|
      - arXiv 论文订阅与推送
    * - 配置持久化
      - |Done|
      - JSON 文件存储配置
    * - Docker 支持
      - |Done|
      - 容器化部署

Repost Bot
==========

features
--------

- 🔗 **GitHub 集成**: 支持接收 GitHub Webhook 的 push、star、fork、issues、PR 等多种事件
- 🎯 **动态配置**: 通过指令动态添加/删除目标群组和订阅事件类型
- 💾 **配置持久化**: 所有配置保存到 JSON 文件，重启后自动加载
- 📊 **统计功能**: 实时统计请求数量和事件分布
- 🏥 **健康检查**: 提供 HTTP 端点查看服务器状态
- 🔌 **插件化**: 模块化设计，易于扩展新功能
- 🐳 **容器化**: 支持 Docker 和 Docker Compose 部署
- 📄 **ArxivRSS**: 附带 arXiv 论文订阅推送插件

支持的 GitHub 事件
------------------

- ``push`` - 代码推送
- ``star`` - 仓库星标
- ``fork`` - 仓库分叉
- ``issues`` - Issue 创建/关闭/重开
- ``issue_comment`` - Issue 评论
- ``pull_request`` - PR 创建/关闭/合并
- ``release`` - 发布新版本
- ``create`` - 创建分支/标签
- ``delete`` - 删除分支/标签
- ``commit_comment`` - 提交评论
- ``ping`` - Webhook 测试


----

Quick Start
===========

Configure File
--------------

编辑 ``config.toml`` 文件，配置适配器和插件：

.. code:: toml

  [bot]
  plugin_dirs = ["plugins"]
  adapters = ["iamai.adapter.cqhttp", "iamai.adapter.apscheduler"]

  [adapter.cqhttp]
  adapter_type = "ws-reverse"
  host = "0.0.0.0"
  port = 3001
  url = "/cqhttp/ws"

  [plugin.webhook]
  host = "0.0.0.0"
  port = 997
  auto_start = true

Running
-------

.. code:: shell

  python main.py

Docker Deployment
-----------------

从 ghcr.io 拉取并自动运行:

.. code:: shell

  docker login ghcr.io
  # 登录密码可以在 Github Settings 里生成一个自己的个人 PAT
  docker run -ai ghcr.io/hydroroll-team/hydroroll-webhook

使用 Docker Compose：

.. code:: shell

  docker-compose up -d

或使用 Docker：

.. code:: shell

  docker build -t hydroroll-webhook .
  docker run -d -p 3001:3001 -p 997:997 -v $(pwd)/data:/iamai/data hydroroll-webhook

----

Webhook Plugin Commands
-----------------------

Server Control
~~~~~~~~~~~~~~

.. code:: text

  /webhook on        - 启动 Webhook 服务器
  /webhook off       - 停止 Webhook 服务器
  /webhook status    - 查看服务器状态
  /webhook stats     - 查看统计信息
  /webhook help      - 显示帮助信息

Group Management
~~~~~~~~~~~~~~~~

.. code:: text

  /webhook addgroup <群号>    - 添加目标群组
  /webhook delgroup <群号>    - 删除目标群组
  /webhook listgroups         - 列出所有目标群组

Event Management
~~~~~~~~~~~~~~~~

.. code:: text

  /webhook addevent <事件类型>   - 启用事件类型
  /webhook delevent <事件类型>   - 禁用事件类型
  /webhook listevents            - 列出已启用的事件

Configure GitHub Webhook
-------------------------

1. 进入 GitHub 仓库的 **Settings** > **Webhooks**
2. 点击 **Add webhook**
3. 配置：

   - **Payload URL**: ``http://服务器IP:997/``
   - **Content type**: ``application/json``
   - **Secret**: 可选
   - **Events**: 选择需要的事件类型

4. 点击 **Add webhook** 保存

Use Examples
------------

.. code:: text

  # 1. 添加目标群组
  /webhook addgroup 123456789

  # 2. 启动服务器
  /webhook on

  # 3. 管理事件订阅
  /webhook addevent push
  /webhook delevent fork
  /webhook listevents

  # 4. 查看状态
  /webhook status
  /webhook stats

----

ArxivRSS Plugin
================

Commands
--------

.. code:: text

  /arxiv set <时> <分>        - 设置订阅推送时间
  /arxiv add <分类>           - 添加订阅分类
  /arxiv del <分类>           - 删除订阅分类
  /arxiv show                 - 显示当前订阅
  /arxiv push [分类]          - 立即推送
  /arxiv kw add <关键词>      - 添加关键词
  /arxiv kw show              - 显示关键词
  /arxiv kw del <关键词>      - 删除关键词

Use Examples
------------

.. code:: text

  # 设置每天 13:00 推送
  /arxiv set 13 00

  # 订阅计算机科学分类
  /arxiv add cs.CV cs.AI

  # 添加关键词
  /arxiv kw add transformer

  # 立即推送
  /arxiv push cs.CV

----

Architecture
============

.. code:: text

  hydroroll-webhook/
  ├── main.py                 # 入口文件
  ├── config.toml             # 配置文件
  ├── plugins/                # 插件目录
  │   ├── webhook/            # Webhook 插件
  │   │   └── __init__.py
  │   └── arxivRSS/           # ArxivRSS 插件
  │       └── __init__.py
  ├── data/                   # 数据目录
  │   └── webhook_config.json # 配置持久化文件
  ├── Dockerfile              # Docker 镜像
  ├── docker-compose.yml      # Docker Compose 配置
  └── README.rst

FAQ
===

Q: 如何修改 Webhook 监听端口？
A:在 ``config.toml`` 中修改 ``[plugin.webhook]`` 的 ``port`` 配置。

Q: 配置文件保存在哪里？
A:配置保存在 ``data/webhook_config.json``，会自动创建。

Q: 如何调试 Webhook？
A: 使用 ``/webhook status`` 查看服务器状态并在 GitHub Webhook 页面查看推送记录, 最后访问 ``http://服务器IP:997/stats`` 查看统计信息

LICENSE
======

AGPLv3 © 2025-PRESENT `HydroRoll-Team`_

.. |logo| image:: https://files.hydroroll.team/hotlink-ok/files/image/logo.png
    :width: 60 
    :target: https://docs.hydroroll.team
.. _iamai: https://iamai.is-a.dev/
.. _go-cqhttp: https://github.com/Mrs4s/go-cqhttp
.. _HydroRoll-Team: https://github.com/HydroRoll-Team

