"""
飞书双向对话 - 使用 larksuite-oapi SDK 长连接模式
"""
import json
import logging
from larksuiteoapi import (
    Config, DOMAIN_FEISHU, Default_client, LogLevel,
)
from larsuiteoapi.event import handle_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_ID = "cli_aacdecf01c7bdcda"
APP_SECRET = "aHmIlG4rPg4udTO7J64NUboeEubkYb7P"


def process_message(text: str) -> str:
    text = text.strip()
    if text.startswith("/"):
        cmd = text[1:].lower().strip()
        if cmd == "status":
            return "系统状态:\n- 后端: PM2 运行中\n- 前端: 运行中\n- 飞书: 长连接已建立"
        elif cmd == "tasks":
            return "当前任务:\n- FS-18: 批量实验 (已完成)\n- 等待新任务"
        else:
            return f"可用命令: /status, /tasks"
    return f"收到: {text}"


def handle_message(event):
    """处理收到的消息事件"""
    try:
        message = event.event.message
        sender = event.event.sender

        if message.message_type == "text":
            content = json.loads(message.content)
            text = content.get("text", "").strip()
            logger.info(f"收到消息: {text}")

            # Process and reply
            from larksuiteoapi import ReplyMessage
            response = process_message(text)

            # Reply using SDK
            reply = ReplyMessage(
                message_id=message.message_id,
                content=json.dumps({"text": response}),
                msg_type="text",
            )
            # Send reply via client
            client.im.v1.message.reply(reply)

    except Exception as e:
        logger.error(f"处理消息失败: {e}")


# 创建配置
config = Config.new_internal_app_settings(
    app_id=APP_ID,
    app_secret=APP_SECRET,
    domain=DOMAIN_FEISHU,
)

# 创建客户端
client = Default_client(config)

# 注册事件处理
client.im.v1.message.register(handle_message)

# 启动长连接
logger.info("启动飞书长连接...")
client.ws.start()
