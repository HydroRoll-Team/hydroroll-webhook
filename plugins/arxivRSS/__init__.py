# original work by HsiangNianian(leader@hydroroll.team)
from iamai.log import logger
from iamai.plugin import Plugin
from iamai import MessageEvent
from iamai.adapter.apscheduler import scheduler_decorator
from iamai.adapter.cqhttp.event import PrivateMessageEvent, GroupMessageEvent
from iamai.adapter.cqhttp.message import CQHTTPMessage, CQHTTPMessageSegment

import os
import re
import feedparser
import json
import time
import ssl
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler

# from .config import Config

master_qq = os.environ.get("MASTER_QQ", "2753364619")
target_group = os.environ.get("TARGET_GROUP", "126211793")
paper_classification = os.environ.get("PAPER_CLASSIFICATION", "cs.CV").split(",")
key_words = os.environ.get("KEY_WORDS", "Sentinel-2,Gaofen-2,Gaofen-1,ICESat-2,tidal,tidal flat,time-series").split(",")

subscribe = Path(__file__).parent / "subscribe.json"
subscribe_list = json.loads(subscribe.read_text("utf-8")) if subscribe.is_file() else {}
scheduler = BackgroundScheduler()


def add_job(bot, user_id):
    scheduler.add_job(
        push_all_arxiv_subscribe,
        "cron",
        args=[
            bot,
            user_id,
            subscribe_list[user_id]["item"],
            subscribe_list[user_id]["keywords"],
        ],
        id=f"arxiv_subscribe_{user_id}",
        replace_existing=True,
        hour=subscribe_list[user_id]["hour"],
        minute=subscribe_list[user_id]["minute"],
    )


def save_subscribe():
    subscribe.write_text(json.dumps(subscribe_list), encoding="utf-8")


def check_subscribe_list():
    for user_id in subscribe_list.keys():
        if "hour" not in subscribe_list[user_id]:
            subscribe_list[user_id]["hour"] = 0
        if "minute" not in subscribe_list[user_id]:
            subscribe_list[user_id]["minute"] = 0
        if "item" not in subscribe_list[user_id]:
            subscribe_list[user_id]["item"] = []
        if "keywords" not in subscribe_list[user_id]:
            subscribe_list[user_id]["keywords"] = []
    save_subscribe()


async def get_arxiv_rss(labels: str):
    if hasattr(ssl, "_create_unverified_context"):
        ssl._create_default_https_context = ssl._create_unverified_context
    news = feedparser.parse(f"http://arxiv.org/rss/{labels}")

    if "version" in news:
        return news.entries
    else:
        logger.info("Failed getting arxiv RSS, try mirror")
        news = feedparser.parse(f"http://arxiv.org/rss/{labels}?mirror=cn")
        if "version" in news:
            return news.entries
        logger.warning(f"Failed getting arxiv RSS with label {labels}")
        return


def get_author(author):
    pattern = re.compile(r">.*?<")
    result = pattern.findall(author)
    author_name = "".join([au[1:-1] for au in result])
    return author_name


def get_summary(summary):
    pattern = re.compile(r"<p>.*?</p>")
    result = pattern.findall(summary.replace("\n", " "))
    author_name = "\n".join([au[3:-4] for au in result])
    return author_name


def check_keywords(text, keywords):
    if len(keywords) > 0:
        pattern = re.compile(f'({"|".join(keywords)})', re.I)
        result = pattern.findall(text)
        # logger.info(result)
        return len(result) > 0
    else:
        return False


def get_link(link):
    link = link.replace("cn.arxiv.org", "arxiv.org")
    return link


async def get_arxiv_subscribe(user_id, label, keywords):
    entries = await get_arxiv_rss(label)
    if entries is None:
        return f"无效的类别 {label} 或网络异常。", None
    elif len(entries) == 0:
        return f"类别{label}今日没有找到论文。", None
    else:
        msg_lists = []
        takeaway_list = []
        msg_list = [
            CQHTTPMessageSegment.node_custom(
                user_id=master_qq,
                nickname="ArxivRSS",
                content=CQHTTPMessage(
                    CQHTTPMessageSegment.text(
                        f"类别{label}今日共找到{len(entries)}篇论文：\n"
                    )
                ),
            )
        ]
        for i in range(len(entries)):
            title = entries[i].title
            # author = get_author(entries[i].author)
            # summary = get_summary(entries[i].summary)
            author = entries[i].author
            summary = entries[i].summary
            msg = f"[{i+1}]{title}\n"
            msg += f"\n{author}\n"
            msg += f"\n{summary}"
            msg_list.append(
                CQHTTPMessageSegment.node_custom(
                    user_id=master_qq,
                    nickname="ArxivRSS",
                    content=CQHTTPMessage(CQHTTPMessageSegment.text(msg)),
                )
            )
            if check_keywords(msg, keywords):
                takeaway_list.append(i + 1)

            msg = get_link(entries[i].link)
            msg_list.append(
                CQHTTPMessageSegment.node_custom(
                    user_id=master_qq,
                    nickname="ArxivRSS",
                    content=CQHTTPMessage(CQHTTPMessageSegment.text(msg)),
                )
            )
            if (i + 1) % 20 == 0:
                msg_lists.append(msg_list)
                msg_list = [
                    CQHTTPMessageSegment.node_custom(
                        user_id=master_qq,
                        nickname="ArxivRSS",
                        content=CQHTTPMessage(
                            CQHTTPMessageSegment.text(
                                f"类别{label}今日共找到{len(entries)}篇论文：\n"
                            )
                        ),
                    )
                ]

        if len(msg_list) > 1:
            msg_lists.append(msg_list)

        if len(takeaway_list) > 0:
            takeaway = f"需要重点关注{takeaway_list}这些文章包含了预定的关键词。"
        else:
            takeaway = None

        return msg_lists, takeaway


async def get_arxiv_subscribe_group(group_id, label, keywords):
    entries = await get_arxiv_rss(label)
    if entries is None:
        return f"无效的类别 {label} 或网络异常。", None
    elif len(entries) == 0:
        return f"类别{label}今日没有找到论文。", None
    else:
        msg_lists = []
        takeaway_list = []
        msg_list = [
            CQHTTPMessageSegment.node_custom(
                user_id=master_qq,
                nickname="ArxivRSS",
                content=CQHTTPMessage(
                    CQHTTPMessageSegment.text(
                        f"类别{label}今日共找到{len(entries)}篇论文：\n"
                    )
                ),
            )
        ]
        for i in range(len(entries)):
            title = entries[i].title
            # author = get_author(entries[i].author)
            # summary = get_summary(entries[i].summary)
            author = entries[i].author
            summary = entries[i].summary
            link = get_link(entries[i].link)
            msg = f"[{i+1}]{title}\n"
            msg += f"\n{author}\n"
            msg += f"\n{summary}"
            msg += f"\n{link}"
            msg_list.append(
                CQHTTPMessageSegment.node_custom(
                    user_id=master_qq,
                    nickname="ArxivRSS",
                    content=CQHTTPMessage(CQHTTPMessageSegment.text(msg)),
                )
            )
            if check_keywords(msg, keywords):
                takeaway_list.append(i + 1)

            # msg = get_link(entries[i].link)
            # msg_list.append(
            #     CQHTTPMessageSegment.node_custom(
            #         user_id=2558978017,
            #         nickname="ArxivRSS",
            #         content=CQHTTPMessage(CQHTTPMessageSegment.text(msg)),
            #     )
            # )
            if (i + 1) % 20 == 0:
                msg_lists.append(msg_list)
                msg_list = [
                    CQHTTPMessageSegment.node_custom(
                        user_id=master_qq,
                        nickname="ArxivRSS",
                        content=CQHTTPMessage(
                            CQHTTPMessageSegment.text(
                                f"类别{label}今日共找到{len(entries)}篇论文：\n"
                            )
                        ),
                    )
                ]

        if len(msg_list) > 1:
            msg_lists.append(msg_list)

        if len(takeaway_list) > 0:
            takeaway = f"需要重点关注{takeaway_list}这些文章包含了预定的关键词。"
        else:
            takeaway = None

        return msg_lists, takeaway


async def push_all_arxiv_subscribe(bot, user_id, labels, keywords):
    for label in labels:
        msg, takeaway = await get_arxiv_subscribe(user_id, label, keywords)
        if type(msg) is list:
            for m in msg:
                await bot.send_private_forward_msg(user_id=int(user_id), messages=m)
                time.sleep(5)
            if takeaway is not None:
                await bot.send_private_msg(user_id=int(user_id), message=takeaway)
        else:
            await bot.send_private_msg(user_id=int(user_id), message=msg)


async def push_all_arxiv_subscribe_group(bot, group_id, labels, keywords):
    for label in labels:
        msg, takeaway = await get_arxiv_subscribe_group(group_id, label, keywords)
        if type(msg) is list:
            for m in msg:
                await bot.send_group_forward_msg(group_id=int(group_id), messages=m)
                time.sleep(5)
            if takeaway is not None:
                await bot.send_group_msg(group_id=int(group_id), message=takeaway)
        else:
            await bot.send_group_msg(group_id=int(group_id), message=msg)


@scheduler_decorator(
    trigger="cron",
    trigger_args={"hour": 13, "minute": 00},
    # trigger_args={"seconds": 60},
    override_rule=True,
)
class ArxivRss(Plugin):
    async def handle(self) -> None:
        bot = self.bot.get_adapter("cqhttp")
        if self.event.type == "apscheduler":
            # await bot.send(  # type: ignore
            #     f"{self.event.type}",
            #     message_type="group",
            #     id_=597049442,
            # )
            await push_all_arxiv_subscribe_group(
                bot,
                target_group,
                paper_classification,
                key_words,
            )
        elif self.event.type == "message":
            args = str(self.event.message).strip("/arxiv").split() or str(
                self.event.message
            )
            logger.debug(f"{args}")
            if args[0] == "add":
                # add category
                if len(args) < 2:
                    await self.event.reply(
                        CQHTTPMessageSegment.text(
                            "在执行add指令时出现错误，您至少需要为其指定一个参数。"
                        )
                    )
                else:
                    user = str(self.event.user_id)
                    if user not in subscribe_list:
                        await self.event.reply(
                            CQHTTPMessageSegment.text(
                                "在执行add指令时出现错误，您首先需要指定一个订阅时间。"
                            )
                        )
                    else:
                        for cate in args[1:]:
                            if cate in subscribe_list[user]["item"]:
                                await self.event.reply(f"类别{cate}已经存在。")
                            else:
                                subscribe_list[user]["item"].append(cate)
                        add_job(bot, user)
                        save_subscribe()
            elif args[0] == "set":
                # set a time for subscription
                if len(args) < 2 or (len(args) == 2 and ":" not in args[1]):
                    await self.event.reply(
                        CQHTTPMessageSegment.text(
                            "在执行set指令时出现错误，您至少需要为其指定两个参数。"
                        )
                    )
                else:
                    user = str(self.event.user_id)
                    if user not in subscribe_list:
                        subscribe_list[user] = {
                            "hour": 0,
                            "minute": 0,
                            "item": [],
                            "keywords": [],
                        }
                    if len(args) == 2:
                        time = args[1].split(":")
                        subscribe_list[user]["hour"] = time[0]
                        subscribe_list[user]["minute"] = time[1]
                    else:
                        subscribe_list[user]["hour"] = args[1]
                        subscribe_list[user]["minute"] = args[2]

                    add_job(bot, user)
                    save_subscribe()
                    await self.event.reply(
                        CQHTTPMessageSegment.text(
                            f"已为您订阅在北京时间{args[1]}:{args[2]}的推送。"
                        )
                    )

            elif args[0] == "cancel":
                # cancel a subscribe
                del subscribe_list[str(self.event.user_id)]
                save_subscribe()
                scheduler.remove_job(f"arxiv_subscribe_{self.event.user_id}")
                await self.event.reply(
                    CQHTTPMessageSegment.text(f"已为您移除可能存在的订阅")
                )

            elif args[0] == "del":
                # remove a category from subscription
                if len(args) < 2:
                    await self.event.reply(
                        CQHTTPMessageSegment.text(
                            "在执行del指令时出现错误，您至少需要为其指定一个参数。"
                        )
                    )
                else:
                    user = str(self.event.user_id)
                    if user not in subscribe_list:
                        await self.event.reply(
                            CQHTTPMessageSegment.text(
                                "在执行del指令时出现错误，您首先需要指定一个订阅时间。"
                            )
                        )
                    else:
                        for cate in args[1:]:
                            if cate not in subscribe_list[user]["item"]:
                                await self.event.reply(f"类别{cate}本就不存在。")
                            else:
                                subscribe_list[user]["item"].remove(cate)
                        add_job(bot, user)
                        save_subscribe()
                        await self.event.reply(f"已移除{len(args)-1}个类别。")

            elif args[0] == "show":
                # show your subscription
                user = str(self.event.user_id)
                if user not in subscribe_list:
                    await self.event.reply(
                        CQHTTPMessageSegment.text("您还没有任何订阅。")
                    )
                else:
                    hh = subscribe_list[user]["hour"]
                    mm = subscribe_list[user]["minute"]
                    item = subscribe_list[user]["item"]
                    await self.event.reply(
                        CQHTTPMessageSegment.text(
                            f"用户{user}的订阅在{hh}:{mm}包含{item}中的内容。"
                        )
                    )

            elif args[0] == "list":
                # list all supported arxiv Category
                await self.event.reply(
                    CQHTTPMessageSegment.text(
                        "例如，cs.CL代表Computation and Language。\n您也可以使用cs获取所有cs类下的内容。\n完整列表请参考https://arxiv.org/category_taxonomy\n"
                    )
                )

            elif args[0] == "push":
                # push RSS right now
                user = str(self.event.user_id)
                if len(args) < 2:
                    # no category, try to use subscription
                    if user in subscribe_list:
                        await push_all_arxiv_subscribe(
                            bot,
                            user,
                            subscribe_list[user]["item"],
                            subscribe_list[user]["keywords"],
                        )
                        # await self.event.reply()
                    else:
                        await self.event.reply(
                            CQHTTPMessageSegment.text(
                                "您至少需要指定一个类别，或至少订阅一个类别。"
                            )
                        )
                else:
                    await push_all_arxiv_subscribe(
                        bot, user, args[1:], subscribe_list[user]["keywords"]
                    )

            elif args[0] == "kw":
                if len(args) < 2:
                    msg = """
    【arxiv kw add <keyword>】
    Add keywords to your subsription. e.g. arxiv kw add self-supervised
    Only one keyword each command

    【arxiv kw show】
    Show the keywords of your subsription.

    【arxiv kw del <keyword>】
    Delete a keyword from your subsription.
    Only one at a time

    【arxiv kw cancel】
    Remove all the keywords of your subsription."""
                    await self.event.reply(CQHTTPMessageSegment.text(msg))
                else:
                    if args[1] == "add":
                        # add keywords
                        if len(args) < 3:
                            await self.event.reply(
                                CQHTTPMessageSegment.text(
                                    "在执行add指令时出现错误，您至少需要为其指定一个参数。"
                                )
                            )
                        else:
                            user = str(self.event.user_id)
                            if user not in subscribe_list:
                                await self.event.reply(
                                    CQHTTPMessageSegment.text(
                                        "在执行add指令时出现错误，您首先需要指定一个订阅时间。"
                                    )
                                )
                            else:
                                cate = " ".join(args[2:])
                                if cate in subscribe_list[user]["keywords"]:
                                    await self.event.reply(f"关键字{cate}已经存在。")
                                else:
                                    subscribe_list[user]["keywords"].append(cate)
                                    add_job(bot, user)
                                    save_subscribe()
                                    await self.event.reply(f"已添加关键字{cate}。")
                    elif args[1] == "show":
                        # show your keywords
                        user = str(self.event.user_id)
                        if user not in subscribe_list:
                            await self.event.reply(
                                CQHTTPMessageSegment.text("您还没有任何订阅。")
                            )
                        else:
                            await self.event.reply(
                                CQHTTPMessageSegment.text(
                                    f"用户{user}关注的关键词有{subscribe_list[user]['keywords']}。"
                                )
                            )
                    elif args[1] == "del":
                        # remove a keyword from subscription
                        if len(args) < 3:
                            await self.event.reply(
                                CQHTTPMessageSegment.text(
                                    "在执行del指令时出现错误，您至少需要为其指定一个参数。"
                                )
                            )
                        else:
                            user = str(self.event.user_id)
                            if user not in subscribe_list:
                                await self.event.reply(
                                    CQHTTPMessageSegment.text(
                                        "在执行del指令时出现错误，您首先需要指定一个订阅时间。"
                                    )
                                )
                            else:
                                cate = " ".join(args[2:])
                                if cate not in subscribe_list[user]["keywords"]:
                                    await self.event.reply(f"关键字{cate}本就不存在。")
                                else:
                                    subscribe_list[user]["keywords"].remove(cate)
                                    add_job(bot, user)
                                    save_subscribe()
                                    await self.event.reply(f"已移除关键字{cate}。")
                    elif args[1] == "cancel":
                        # cancel keywords
                        user = str(self.event.user_id)
                        if user not in subscribe_list:
                            await self.event.reply(
                                CQHTTPMessageSegment.text("您还没有任何订阅。")
                            )
                        subscribe_list[user]["keywords"] = []
                        add_job(bot, user)
                        save_subscribe()
                        await self.event.reply(
                            CQHTTPMessageSegment.text(f"已为您移除可能存在的关键词")
                        )
                    else:
                        await self.event.reply(
                            CQHTTPMessageSegment.text(
                                f"未知的命令{self.event.message.get_plain_text()}"
                            )
                        )
            else:
                await self.event.reply(
                    """arxiv <option> [args]

        Private Conversation Only

        Usage:
        【arxiv add [category]】
        Add a new category to your subscription. 
        Category should be Arxiv Category like cs (for computer science) or cs.CL (for computation and language). 
        Use "arxiv list" to get all supported categories.
        You should use "arxiv set hh mm" to setup a subscription before you add any category

        【arxiv del [category]】
        Remove a category of your subscription.

        【arxiv set hh mm】
        Subscribe at hh:mm.

        【arxiv cancel】
        Cancel your subscription

        【arxiv show】
        List your subscription and time

        【arxiv list】
        List all supported arxiv category

        【arxiv push [category]】
        Push arxiv RSS right now. If category is not specified, will use user's subscription.
        For example, "arxiv push" or "arxiv push cs.CL eess.AS"

        【arxiv kw add <keyword>】
        Add keywords to your subsription. e.g. arxiv kw add self-supervised
        Only one keyword each command

        【arxiv kw show】
        Show the keywords of your subsription.

        【arxiv kw del <keyword>】
        Delete a keyword from your subsription.
        Only one at a time

        【arxiv kw cancel】
        Remove all the keywords of your subsription.
        """
                )

    async def rule(self) -> bool:
        return bool(
            self.event.type == "message"
            and self.event.user_id == master_qq
            and (self.event.message.get_plain_text().lower().startswith("/arxiv"))
        )