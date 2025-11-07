"""
HydroRoll Webhook Plugin - Advanced Version
支持配置文件、多群推送、事件过滤等高级特性
"""
from aiohttp import web
from iamai import Plugin, ConfigModel
from iamai.log import logger
from iamai.adapter.cqhttp.message import CQHTTPMessageSegment as ms
from typing import Optional, List, Dict, Any
from pydantic import Field
import asyncio
import re

# 全局单例服务器实例
_global_webhook_server: Optional['WebhookServer'] = None


class WebhookPluginConfig(ConfigModel):
    """Webhook 插件配置"""
    
    __config_name__: str = "webhook"
    
    # 服务器配置
    host: str = Field(default="0.0.0.0", description="监听地址")
    port: int = Field(default=997, description="监听端口")
    auto_start: bool = Field(default=True, description="是否自动启动")
    
    # 消息推送配置
    target_groups: List[int] = Field(default=[126211793], description="目标 QQ 群列表")
    
    # 事件过滤配置
    enabled_events: List[str] = Field(
        default=[
            "push", "star", "fork", "issues", "issue_comment",
            "pull_request", "release", "create", "delete",
            "commit_comment", "ping"
        ],
        description="启用的事件类型"
    )
    
    # 高级配置
    max_commit_display: int = Field(default=5, description="最多显示的提交数量")
    truncate_comment: int = Field(default=100, description="评论截断长度")
    filter_bots: bool = Field(default=False, description="是否过滤机器人事件")


# 事件描述模板
EVENT_DESCRIPTIONS = {
    "ping": "🏓 Webhook connection test successful!",
    "push": "📮 [{repository[full_name]}] {pusher[name]} pushed {commits_count} commit(s) to {ref}:\n{pushes}",
    "star": {
        "created": "💗 [{repository[full_name]}] {sender[login]} starred the repository! Total: {repository[stargazers_count]}⭐",
        "deleted": "💔 [{repository[full_name]}] {sender[login]} unstarred the repository. Total: {repository[stargazers_count]}⭐"
    },
    "fork": "🍴 [{repository[full_name]}] {sender[login]} forked the repository! Total: {repository[forks_count]}🍴",
    "create": "🆕 [{repository[full_name]}] {sender[login]} created {ref_type}: {ref}",
    "delete": "🗑️ [{repository[full_name]}] {sender[login]} deleted {ref_type}: {ref}",
    "issues": {
        "opened": "📝 [{repository[full_name]}] {sender[login]} opened issue #{issue[number]}: {issue[title]}\n🔗 {issue[html_url]}",
        "closed": "✅ [{repository[full_name]}] {sender[login]} closed issue #{issue[number]}: {issue[title]}",
        "reopened": "🔄 [{repository[full_name]}] {sender[login]} reopened issue #{issue[number]}: {issue[title]}"
    },
    "issue_comment": {
        "created": "💬 [{repository[full_name]}] {sender[login]} commented on issue #{issue[number]}:\n{comment_text}",
        "edited": "✏️ [{repository[full_name]}] {sender[login]} edited comment on issue #{issue[number]}",
        "deleted": "🗑️ [{repository[full_name]}] {sender[login]} deleted comment on issue #{issue[number]}"
    },
    "pull_request": {
        "opened": "🔀 [{repository[full_name]}] {sender[login]} opened PR #{pull_request[number]}: {pull_request[title]}\n🔗 {pull_request[html_url]}",
        "closed": "✅ [{repository[full_name]}] {sender[login]} closed PR #{pull_request[number]}: {pull_request[title]}",
        "reopened": "🔄 [{repository[full_name]}] {sender[login]} reopened PR #{pull_request[number]}: {pull_request[title]}",
        "merged": "🎉 [{repository[full_name]}] {sender[login]} merged PR #{pull_request[number]}: {pull_request[title]}"
    },
    "release": {
        "published": "🚀 [{repository[full_name]}] Released {release[tag_name]}: {release[name]}\n🔗 {release[html_url]}",
        "created": "📦 [{repository[full_name]}] Created release {release[tag_name]}: {release[name]}"
    },
    "commit_comment": {
        "created": "💭 [{repository[full_name]}] {sender[login]} commented on commit {comment[commit_id][:7]}"
    }
}


class WebhookServer:
    """Webhook 服务器管理类（单例模式）"""
    
    def __init__(self, config: WebhookPluginConfig):
        self.config = config
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.app: Optional[web.Application] = None
        self.plugins: List['HydroRollWebhookAdvanced'] = []  # 支持多个插件实例
        self.is_running = False
        
        # 统计信息
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "events_by_type": {},
            "registered_plugins": 0
        }
    
    def register_plugin(self, plugin: 'HydroRollWebhookAdvanced'):
        """注册插件实例"""
        if plugin not in self.plugins:
            self.plugins.append(plugin)
            self.stats["registered_plugins"] = len(self.plugins)
            logger.info(f"Registered plugin instance: {plugin.name} (total: {len(self.plugins)})")
    
    def unregister_plugin(self, plugin: 'HydroRollWebhookAdvanced'):
        """注销插件实例"""
        if plugin in self.plugins:
            self.plugins.remove(plugin)
            self.stats["registered_plugins"] = len(self.plugins)
            logger.info(f"Unregistered plugin instance: {plugin.name} (remaining: {len(self.plugins)})")
    
    async def start(self) -> bool:
        """启动 Webhook 服务器"""
        if self.is_running:
            logger.info("Webhook server is already running")
            return True  # 已运行视为成功
        
        try:
            self.app = web.Application()
            self.app.router.add_post("/", self.handle_webhook)
            self.app.router.add_get("/", self.handle_health_check)
            self.app.router.add_get("/stats", self.handle_stats)
            
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, self.config.host, self.config.port)
            await self.site.start()
            
            self.is_running = True
            logger.info(f"Webhook server started on {self.config.host}:{self.config.port}")
            logger.info(f"Registered {len(self.plugins)} plugin instance(s)")
            return True
            
        except OSError as e:
            if "address already in use" in str(e).lower():
                logger.warning(f"Port {self.config.port} is already in use. Server may already be running.")
                # 端口已被占用，可能是已经启动了
                self.is_running = True
                return True
            logger.error(f"Failed to start webhook server: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return False
    
    async def stop(self) -> bool:
        """停止 Webhook 服务器"""
        if not self.is_running:
            return False
        
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            
            self.is_running = False
            logger.info("Webhook server stopped")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping server: {e}")
            return False
    
    async def handle_health_check(self, request: web.Request) -> web.Response:
        """健康检查端点"""
        return web.json_response({
            "status": "healthy",
            "running": self.is_running,
            "stats": self.stats
        })
    
    async def handle_stats(self, request: web.Request) -> web.Response:
        """统计信息端点"""
        return web.json_response(self.stats)
    
    async def handle_webhook(self, request: web.Request) -> web.Response:
        """处理 Webhook 请求"""
        self.stats["total_requests"] += 1
        
        try:
            data = await request.json()
            event_type = request.headers.get("X-GitHub-Event")
            
            if not event_type:
                logger.warning("Missing X-GitHub-Event header")
                self.stats["failed_requests"] += 1
                return web.json_response({"error": "Missing X-GitHub-Event header"}, status=400)
            
            # 更新统计
            self.stats["events_by_type"][event_type] = self.stats["events_by_type"].get(event_type, 0) + 1
            
            logger.debug(f"Received webhook: {event_type}")
            
            # 检查事件是否启用
            if event_type not in self.config.enabled_events:
                logger.debug(f"Event {event_type} is disabled")
                return web.json_response({"message": "Event type disabled"})
            
            # 过滤机器人事件
            if self.config.filter_bots and data.get("sender", {}).get("type") == "Bot":
                logger.debug("Filtered bot event")
                return web.json_response({"message": "Bot event filtered"})
            
            # 使用第一个可用的插件实例格式化消息
            message = None
            for plugin in self.plugins:
                if plugin and hasattr(plugin, '_format_event'):
                    message = plugin._format_event(event_type=event_type, data=data)
                    if message:
                        break
            
            if message:
                await self._send_to_groups(message)
                self.stats["successful_requests"] += 1
                logger.info(f"Processed {event_type} event successfully")
            else:
                logger.warning(f"Empty message for {event_type}")
            
            return web.json_response({"message": "Received"})
            
        except Exception as e:
            self.stats["failed_requests"] += 1
            logger.error(f"Error handling webhook: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def _send_to_groups(self, message: str):
        """发送消息到多个群"""
        # 使用第一个可用的插件实例
        plugin = None
        for p in self.plugins:
            if p and hasattr(p, 'bot') and p.bot:
                plugin = p
                break
        
        if not plugin or not plugin.bot:
            logger.error("No plugin with bot available")
            return
        
        # 获取 CQHTTP 适配器
        cqhttp_adapter = None
        for adapter in plugin.bot.adapters:
            if adapter.name == "cqhttp":
                cqhttp_adapter = adapter
                break
        
        if not cqhttp_adapter:
            logger.error("CQHTTP adapter not found")
            return
        
        # 发送到所有配置的群
        for group_id in self.config.target_groups:
            try:
                await cqhttp_adapter.call_api(
                    "send_group_msg",
                    group_id=group_id,
                    message=message
                )
                logger.debug(f"Message sent to group {group_id}")
            except Exception as e:
                logger.error(f"Failed to send to group {group_id}: {e}")


class HydroRollWebhookAdvanced(Plugin):
    """
    HydroRoll Webhook 插件 - 高级版
    
    特性：
    - 配置文件支持
    - 多群推送
    - 事件过滤
    - 统计信息
    - 健康检查
    - 单例模式（支持多个插件实例共享同一服务器）
    """
    
    priority: int = 10
    block: bool = False
    
    Config = WebhookPluginConfig
    
    def __init__(self):
        super().__init__()
        self.server: Optional[WebhookServer] = None
        
        # 延迟初始化，确保 config 可用
        asyncio.create_task(self._initialize())
    
    async def _initialize(self):
        """异步初始化"""
        global _global_webhook_server
        
        await asyncio.sleep(1)  # 等待 bot 初始化
        
        try:
            # 使用全局单例服务器
            if _global_webhook_server is None:
                logger.info(f"Creating new webhook server instance for {self.name}")
                _global_webhook_server = WebhookServer(self.config)
                self.server = _global_webhook_server
            else:
                logger.info(f"Reusing existing webhook server instance for {self.name}")
                self.server = _global_webhook_server
            
            # 注册当前插件实例
            self.server.register_plugin(self)
            
            # 自动启动（如果还未启动）
            if self.config.auto_start and not self.server.is_running:
                success = await self.server.start()
                if success:
                    logger.info(f"Webhook server auto-started by {self.name}")
                    logger.info(f"Configuration: host={self.config.host}, port={self.config.port}")
                    logger.info(f"Target groups: {self.config.target_groups}")
                else:
                    logger.error("Failed to auto-start webhook server")
            elif self.server.is_running:
                logger.info(f"Webhook server already running (registered by {self.name})")
        except Exception as e:
            logger.error(f"Error initializing webhook plugin: {e}", exc_info=True)
    
    async def handle(self) -> None:
        """处理命令"""
        message = str(self.event.message).strip()
        
        commands = {
            "HydroRoll on": self._cmd_start,
            "HydroRoll off": self._cmd_stop,
            "HydroRoll status": self._cmd_status,
            "HydroRoll stats": self._cmd_stats,
            "HydroRoll help": self._cmd_help,
        }
        
        handler = commands.get(message)
        if handler:
            await handler()
    
    async def _cmd_start(self):
        """启动服务器"""
        if not self.server:
            await self.event.reply("Server not initialized")
            return
        
        if self.server.is_running:
            await self.event.reply("✅ Server is already running")
        else:
            success = await self.server.start()
            if success:
                await self.event.reply(
                    f"✅ Server started on {self.config.host}:{self.config.port}\n"
                    f"Target groups: {', '.join(map(str, self.config.target_groups))}\n"
                    f"Registered plugins: {len(self.server.plugins)}"
                )
            else:
                await self.event.reply("❌ Failed to start server")
    
    async def _cmd_stop(self):
        """停止服务器"""
        if not self.server:
            await self.event.reply("Server not initialized")
            return
        
        if not self.server.is_running:
            await self.event.reply("Server is not running")
        else:
            success = await self.server.stop()
            if success:
                await self.event.reply("✅ Server stopped")
            else:
                await self.event.reply("❌ Failed to stop server")
    
    async def _cmd_status(self):
        """查询状态"""
        if not self.server:
            await self.event.reply("Server not initialized")
            return
        
        status = "🟢 Running" if self.server.is_running else "🔴 Stopped"
        message = f"Status: {status}\n"
        
        if self.server.is_running:
            message += f"Address: {self.config.host}:{self.config.port}\n"
            message += f"Groups: {', '.join(map(str, self.config.target_groups))}\n"
            message += f"Registered plugins: {len(self.server.plugins)}\n"
            message += f"Requests: {self.server.stats['total_requests']}"
        
        await self.event.reply(message)
    
    async def _cmd_stats(self):
        """查询统计信息"""
        if not self.server:
            await self.event.reply("Server not initialized")
            return
        
        stats = self.server.stats
        message = f"📊 Statistics:\n"
        message += f"Total requests: {stats['total_requests']}\n"
        message += f"✅ Successful: {stats['successful_requests']}\n"
        message += f"❌ Failed: {stats['failed_requests']}\n\n"
        message += "Events received:\n"
        
        for event_type, count in sorted(stats['events_by_type'].items(), key=lambda x: x[1], reverse=True):
            message += f"  {event_type}: {count}\n"
        
        await self.event.reply(message.strip())
    
    async def _cmd_help(self):
        """显示帮助"""
        help_text = """
🤖 HydroRoll Webhook Commands:

HydroRoll on - Start webhook server
HydroRoll off - Stop webhook server  
HydroRoll status - Show server status
HydroRoll stats - Show statistics
HydroRoll help - Show this help
        """.strip()
        await self.event.reply(help_text)
    
    async def rule(self) -> bool:
        """匹配规则"""
        if self.event.adapter.name != "cqhttp":
            return False
        
        if self.event.type != "message":
            return False
        
        message = str(self.event.message).strip()
        return message.startswith("HydroRoll ")
    
    def _format_event(self, event_type: str, data: Dict[str, Any]) -> Optional[str]:
        """格式化事件消息"""
        try:
            template = EVENT_DESCRIPTIONS.get(event_type)
            if not template:
                return None
            
            # 处理字典模板
            if isinstance(template, dict):
                action = data.get("action")
                if action not in template:
                    return None
                template = template[action]
            
            # 预处理数据
            processed_data = self._preprocess_data(event_type, data)
            
            # 格式化
            return template.format(**processed_data)
            
        except Exception as e:
            logger.error(f"Error formatting event: {e}", exc_info=True)
            return None
    
    def _preprocess_data(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """预处理事件数据"""
        processed = dict(data)
        
        # 处理 push 事件
        if event_type == "push" and "commits" in data:
            commits = data["commits"][:self.config.max_commit_display]
            commits_text = "\n".join(
                f"  [{c['id'][:7]}] {c['message'].split(chr(10))[0]}"
                for c in commits
            )
            
            if len(data["commits"]) > self.config.max_commit_display:
                commits_text += f"\n  ... and {len(data['commits']) - self.config.max_commit_display} more"
            
            processed["pushes"] = commits_text
            processed["commits_count"] = len(data["commits"])
        
        # 处理评论
        if "comment" in data and "body" in data["comment"]:
            comment = data["comment"]["body"]
            if len(comment) > self.config.truncate_comment:
                processed["comment_text"] = comment[:self.config.truncate_comment] + "..."
            else:
                processed["comment_text"] = comment
        
        return processed
