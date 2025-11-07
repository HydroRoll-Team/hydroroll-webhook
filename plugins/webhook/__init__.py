from aiohttp import web
from iamai import Plugin, ConfigModel
from iamai.log import logger
from iamai.adapter.cqhttp.message import CQHTTPMessageSegment as ms
from typing import Optional, List, Dict, Any
from pydantic import Field
import asyncio
import json
import os
from pathlib import Path

_global_webhook_server: Optional['WebhookServer'] = None


class WebhookPluginConfig(ConfigModel):
    """Webhook 插件配置"""
    
    __config_name__: str = "webhook"
    
    host: str = Field(default="0.0.0.0", description="监听地址")
    port: int = Field(default=997, description="监听端口")
    auto_start: bool = Field(default=True, description="是否自动启动")
    
    max_commit_display: int = Field(default=5, description="最多显示的提交数量")
    truncate_comment: int = Field(default=100, description="评论截断长度")
    filter_bots: bool = Field(default=False, description="是否过滤机器人事件")
    data_file: str = Field(default="data/webhook_config.json", description="配置数据文件路径")


class WebhookDataManager:
    """Webhook 数据管理类 - 负责配置的持久化"""
    
    def __init__(self, data_file: str):
        self.data_file = Path(data_file)
        self.data = {
            "enabled": False,
            "target_groups": [],
            "enabled_events": [
                "push", "star", "fork", "issues", "issue_comment",
                "pull_request", "release", "create", "delete",
                "commit_comment", "ping"
            ]
        }
        self._load()
    
    def _load(self):
        """从文件加载配置"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    self.data.update(loaded_data)
                    logger.info(f"Loaded webhook config from {self.data_file}")
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
        else:
            logger.info("No existing config file, using defaults")
            self._save()
    
    def _save(self):
        """保存配置到文件"""
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved webhook config to {self.data_file}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
    
    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self.data.get("enabled", False)
    
    def set_enabled(self, enabled: bool):
        """设置启用状态"""
        self.data["enabled"] = enabled
        self._save()
    
    def get_target_groups(self) -> List[int]:
        """获取目标群组列表"""
        return self.data.get("target_groups", [])
    
    def add_target_group(self, group_id: int) -> bool:
        """添加目标群组"""
        if group_id not in self.data["target_groups"]:
            self.data["target_groups"].append(group_id)
            self._save()
            return True
        return False
    
    def remove_target_group(self, group_id: int) -> bool:
        """移除目标群组"""
        if group_id in self.data["target_groups"]:
            self.data["target_groups"].remove(group_id)
            self._save()
            return True
        return False
    
    def get_enabled_events(self) -> List[str]:
        """获取启用的事件列表"""
        return self.data.get("enabled_events", [])
    
    def add_event(self, event_type: str) -> bool:
        """添加事件类型"""
        if event_type not in self.data["enabled_events"]:
            self.data["enabled_events"].append(event_type)
            self._save()
            return True
        return False
    
    def remove_event(self, event_type: str) -> bool:
        """移除事件类型"""
        if event_type in self.data["enabled_events"]:
            self.data["enabled_events"].remove(event_type)
            self._save()
            return True
        return False
    
    def is_event_enabled(self, event_type: str) -> bool:
        """检查事件是否启用"""
        return event_type in self.data.get("enabled_events", [])


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
    
    def __init__(self, config: WebhookPluginConfig, bot):
        self.config = config
        self.data_manager = WebhookDataManager(config.data_file)
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.app: Optional[web.Application] = None
        self.plugins: List['HydroRollWebhook'] = []
        self.is_running = False
        
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "events_by_type": {},
            "registered_plugins": 0
        }
    
    def register_plugin(self, plugin: 'HydroRollWebhook'):
        """注册插件实例"""
        if plugin not in self.plugins:
            self.plugins.append(plugin)
            self.stats["registered_plugins"] = len(self.plugins)
            logger.info(f"Registered plugin instance (total: {len(self.plugins)})")
    
    def unregister_plugin(self, plugin: 'HydroRollWebhook'):
        """注销插件实例"""
        if plugin in self.plugins:
            self.plugins.remove(plugin)
            self.stats["registered_plugins"] = len(self.plugins)
            logger.info(f"Unregistered plugin instance (remaining: {len(self.plugins)})")
    
    async def start(self) -> bool:
        """启动 Webhook 服务器"""
        if self.is_running:
            logger.info("Webhook server is already running")
            return True
        
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
            
            self.stats["events_by_type"][event_type] = self.stats["events_by_type"].get(event_type, 0) + 1
            
            logger.debug(f"Received webhook: {event_type}")
            
            if not self.data_manager.is_event_enabled(event_type):
                logger.debug(f"Event {event_type} is disabled")
                return web.json_response({"message": "Event type disabled"})
            
            if self.config.filter_bots and data.get("sender", {}).get("type") == "Bot":
                logger.debug("Filtered bot event")
                return web.json_response({"message": "Bot event filtered"})
            

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
        target_groups = self.data_manager.get_target_groups()
        if not target_groups:
            logger.warning("No target groups configured")
            return
        
        for group_id in target_groups:
            try:
                await self.event.adapter.call_api(
                    "send_group_msg",
                    group_id=group_id,
                    message=message
                )
                logger.debug(f"Message sent to group {group_id}")
            except Exception as e:
                logger.error(f"Failed to send to group {group_id}: {e}")


class HydroRollWebhook(Plugin):
    priority: int = 10
    block: bool = False
    
    Config = WebhookPluginConfig
    
    async def _ensure_initialized(self):
        """确保服务器已初始化（惰性初始化）"""
        global _global_webhook_server
        
        if _global_webhook_server is not None:
            return _global_webhook_server
        
        try:
            logger.info("Creating new webhook server instance")
            _global_webhook_server = WebhookServer(self.config, self.bot)
            _global_webhook_server.register_plugin(self)
            
            # 根据配置文件决定是否自动启动
            if self.config.auto_start and _global_webhook_server.data_manager.is_enabled():
                success = await _global_webhook_server.start()
                if success:
                    logger.info("Webhook server auto-started")
                    logger.info(f"Configuration: host={self.config.host}, port={self.config.port}")
                    logger.info(f"Target groups: {_global_webhook_server.data_manager.get_target_groups()}")
                else:
                    logger.error("Failed to auto-start webhook server")
            
            return _global_webhook_server
            
        except Exception as e:
            logger.error(f"Error initializing webhook plugin: {e}", exc_info=True)
            raise
    
    async def handle(self) -> None:
        """处理命令"""
        server = await self._ensure_initialized()
        
        if not server:
            await self.event.reply("Server initialization failed")
            return
        
        message = str(self.event.message).strip()
        parts = message.split()
        
        if len(parts) < 2:
            await self._cmd_help()
            return
        
        command = parts[1]
        
        commands = {
            "on": self._cmd_start,
            "off": self._cmd_stop,
            "status": self._cmd_status,
            "stats": self._cmd_stats,
            "help": self._cmd_help,
            "addgroup": self._cmd_add_group,
            "delgroup": self._cmd_del_group,
            "listgroups": self._cmd_list_groups,
            "addevent": self._cmd_add_event,
            "delevent": self._cmd_del_event,
            "listevents": self._cmd_list_events,
        }
        
        handler = commands.get(command)
        if handler:
            await handler()
        else:
            await self.event.reply(f"Unknown command: {command}\nUse /webhook help for available commands")
    
    async def _cmd_add_group(self):
        """添加目标群组"""
        server = _global_webhook_server
        if not server:
            await self.event.reply("Server not initialized")
            return
        
        message = str(self.event.message).strip()
        parts = message.split()
        
        if len(parts) < 3:
            await self.event.reply("Usage: /webhook addgroup <group_id>")
            return
        
        try:
            group_id = int(parts[2])
            if server.data_manager.add_target_group(group_id):
                await self.event.reply(f"Added group {group_id} to target list")
            else:
                await self.event.reply(f"Group {group_id} already in target list")
        except ValueError:
            await self.event.reply("Invalid group ID")
    
    async def _cmd_del_group(self):
        """删除目标群组"""
        server = _global_webhook_server
        if not server:
            await self.event.reply("❌ Server not initialized")
            return
        
        message = str(self.event.message).strip()
        parts = message.split()
        
        if len(parts) < 3:
            await self.event.reply("Usage: /webhook delgroup <group_id>")
            return
        
        try:
            group_id = int(parts[2])
            if server.data_manager.remove_target_group(group_id):
                await self.event.reply(f"Removed group {group_id} from target list")
            else:
                await self.event.reply(f"Group {group_id} not in target list")
        except ValueError:
            await self.event.reply("Invalid group ID")

    async def _cmd_list_groups(self):
        """列出所有目标群组"""
        server = _global_webhook_server
        if not server:
            await self.event.reply("Server not initialized")
            return
        
        groups = server.data_manager.get_target_groups()
        if groups:
            group_list = "\n".join(f"  • {gid}" for gid in groups)
            await self.event.reply(f"Target Groups ({len(groups)}):\n{group_list}")
        else:
            await self.event.reply("No target groups configured")
    
    async def _cmd_add_event(self):
        """添加事件类型"""
        server = _global_webhook_server
        if not server:
            await self.event.reply("Server not initialized")
            return
        
        message = str(self.event.message).strip()
        parts = message.split()
        
        if len(parts) < 3:
            await self.event.reply("Usage: /webhook addevent <event_type>")
            return
        
        event_type = parts[2]
        if server.data_manager.add_event(event_type):
            await self.event.reply(f"Added event type: {event_type}")
        else:
            await self.event.reply(f"Event type {event_type} already enabled")
    
    async def _cmd_del_event(self):
        """删除事件类型"""
        server = _global_webhook_server
        if not server:
            await self.event.reply("❌ Server not initialized")
            return
        
        message = str(self.event.message).strip()
        parts = message.split()
        
        if len(parts) < 3:
            await self.event.reply("Usage: /webhook delevent <event_type>")
            return
        
        event_type = parts[2]
        if server.data_manager.remove_event(event_type):
            await self.event.reply(f"Removed event type: {event_type}")
        else:
            await self.event.reply(f"Event type {event_type} not enabled")
    
    async def _cmd_list_events(self):
        """列出所有启用的事件"""
        server = _global_webhook_server
        if not server:
            await self.event.reply("Server not initialized")
            return
        
        events = server.data_manager.get_enabled_events()
        if events:
            event_list = "\n".join(f"  • {evt}" for evt in events)
            await self.event.reply(f"Enabled Events ({len(events)}):\n{event_list}")
        else:
            await self.event.reply("No events enabled")
    
    async def _cmd_start(self):
        """启动服务器"""
        server = _global_webhook_server
        if not server:
            await self.event.reply("Server not initialized")
            return
        
        if server.is_running:
            await self.event.reply("Server is already running")
        else:
            success = await server.start()
            if success:
                server.data_manager.set_enabled(True)
                groups = server.data_manager.get_target_groups()
                await self.event.reply(
                    f"Server started on {self.config.host}:{self.config.port}\n"
                    f"Target groups: {', '.join(map(str, groups)) if groups else 'None'}\n"
                    f"Registered plugins: {len(server.plugins)}"
                )
            else:
                await self.event.reply("Failed to start server")
    
    async def _cmd_stop(self):
        """停止服务器"""
        server = _global_webhook_server
        if not server:
            await self.event.reply("Server not initialized")
            return
        
        if not server.is_running:
            await self.event.reply("Server is not running")
        else:
            success = await server.stop()
            if success:
                server.data_manager.set_enabled(False)
                await self.event.reply("Server stopped")
            else:
                await self.event.reply("Failed to stop server")

    async def _cmd_status(self):
        """查询状态"""
        server = _global_webhook_server
        if not server:
            await self.event.reply("Server not initialized")
            return
        
        status = "Running" if server.is_running else "Stopped"
        message = f"Server Status: {status}\n"
        
        if server.is_running:
            message += f"Address: {self.config.host}:{self.config.port}\n"
            groups = server.data_manager.get_target_groups()
            message += f"Groups: {', '.join(map(str, groups)) if groups else 'None'}\n"
            message += f"Registered plugins: {len(server.plugins)}\n"
            message += f"Requests: {server.stats['total_requests']}"
        
        await self.event.reply(message)
    
    async def _cmd_stats(self):
        """查询统计信息"""
        server = _global_webhook_server
        if not server:
            await self.event.reply("Server not initialized")
            return
        
        stats = server.stats
        message = f"Statistics:\n"
        message += f"Total requests: {stats['total_requests']}\n"
        message += f"Successful: {stats['successful_requests']}\n"
        message += f"Failed: {stats['failed_requests']}\n\n"
        message += f"Events received:\n"
        
        if stats['events_by_type']:
            for event_type, count in sorted(stats['events_by_type'].items(), key=lambda x: x[1], reverse=True):
                message += f"  • {event_type}: {count}\n"
        else:
            message += "  No events received yet\n"
        
        await self.event.reply(message.strip())
    
    async def _cmd_help(self):
        """显示帮助"""
        help_text = """Webhook Commands:

Server Control:
  /webhook on - Start webhook server
  /webhook off - Stop webhook server
  /webhook status - Show server status
  /webhook stats - Show statistics

Group Management:
  /webhook addgroup <group_id> - Add target group
  /webhook delgroup <group_id> - Remove target group
  /webhook listgroups - List all target groups

Event Management:
  /webhook addevent <event_type> - Enable event type
  /webhook delevent <event_type> - Disable event type
  /webhook listevents - List enabled events

Available event types:
  push, star, fork, issues, issue_comment,
  pull_request, release, create, delete,
  commit_comment, ping
        """.strip()
        await self.event.reply(help_text)
    
    async def rule(self) -> bool:
        if self.event.adapter.name != "cqhttp":
            return False
        
        if self.event.type != "message":
            return False
        
        message = str(self.event.message).strip()
        return message.startswith("/webhook")
    
    def _format_event(self, event_type: str, data: Dict[str, Any]) -> Optional[str]:
        """格式化事件消息"""
        try:
            template = EVENT_DESCRIPTIONS.get(event_type)
            if not template:
                return None
            
            if isinstance(template, dict):
                action = data.get("action")
                if action not in template:
                    return None
                template = template[action]
            
            processed_data = self._preprocess_data(event_type, data)
            
            return template.format(**processed_data)
            
        except Exception as e:
            logger.error(f"Error formatting event: {e}", exc_info=True)
            return None
    
    def _preprocess_data(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """预处理事件数据"""
        processed = dict(data)
        
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
        
        if "comment" in data and "body" in data["comment"]:
            comment = data["comment"]["body"]
            if len(comment) > self.config.truncate_comment:
                processed["comment_text"] = comment[:self.config.truncate_comment] + "..."
            else:
                processed["comment_text"] = comment
        
        return processed
