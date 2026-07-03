"""
飞书双向对话 - larksuite-oapi SDK 长连接
"""
import json
import logging
import time
import requests

from larksuiteoapi import (
    Config, DOMAIN_FEISHU, set_event_callback,
    HTTPEvent, OapiRequest, OapiResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_ID = "cli_aacdecf01c7bdcda"
APP_SECRET = "aHmIlG4rPg4udTO7J64NUboeEubkYb7P"

_token_cache = {"token": None, "expires_at": 0}


def get_token():
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now:
        return _token_cache["token"]
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
    )
    data = resp.json()
    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expires_at"] = now + data["expire"] - 300
    return _token_cache["token"]


def reply_message(message_id: str, text: str):
    token = get_token()
    resp = requests.post(
        f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"content": json.dumps({"text": text}), "msg_type": "text"},
    )
    return resp.json()


def process_message(text: str) -> str:
    text = text.strip()
    if text.startswith("/"):
        cmd = text[1:].lower().strip()
        if cmd == "status":
            return "系统状态:\n- 后端: PM2 运行中\n- 前端: 运行中\n- 飞书: 长连接已建立"
        elif cmd == "tasks":
            return "当前任务:\n- FS-18: 批量实验 (已完成)\n- 等待新任务"
        else:
            return "可用命令: /status, /tasks"
    return f"收到: {text}"


# Create config
conf = Config.new_internal_app_settings(
    app_id=APP_ID,
    app_secret=APP_SECRET,
)
conf.domain = DOMAIN_FEISHU


@set_event_callback(conf, "im.message.receive_v1")
def handle_message_event(conf: Config, event: dict):
    """Handle incoming message events"""
    try:
        message = event.get("event", {}).get("message", {})
        message_id = message.get("message_id", "")

        if message.get("message_type") == "text":
            content = json.loads(message.get("content", "{}"))
            text = content.get("text", "").strip()
            logger.info(f"收到消息: {text}")

            response = process_message(text)
            if message_id:
                reply_message(message_id, response)
                logger.info(f"已回复: {response[:30]}...")

    except Exception as e:
        logger.error(f"处理消息错误: {e}")


def start_ws():
    """Start WebSocket long connection using SDK"""
    logger.info("启动飞书 WebSocket 长连接...")

    # Use SDK's built-in WS client
    from larksuiteoapi import ws

    # Create WS client
    client = ws.Client(
        app_id=APP_ID,
        app_secret=APP_SECRET,
        domain=DOMAIN_FEISHU,
        log_level=logging.INFO,
    )

    # Register event handler
    client.register_callback("im.message.receive_v1", lambda c, e: handle_message_event(c, e))

    # Start
    client.start()
    logger.info("✓ 飞书双向对话已启动")


if __name__ == "__main__":
    start_ws()
