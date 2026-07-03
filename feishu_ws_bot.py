"""
飞书双向对话 - 使用 larksuite-oapi SDK 长连接模式
"""
import json
import logging
import time
import requests
import websocket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_ID = "cli_aacdecf01c7bdcda"
APP_SECRET = "aHmIlG4rPg4udTO7J64NUboeEubkYb7P"

# Token cache
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
    logger.info(f"Reply response: {resp.json()}")
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


def on_message(ws, message):
    try:
        event = json.loads(message)
        header = event.get("header", {})
        event_type = header.get("event_type", "")

        if event_type == "im.message.receive_v1":
            msg = event.get("event", {}).get("message", {})
            msg_type = msg.get("message_type", "")
            message_id = msg.get("message_id", "")

            if msg_type == "text":
                content = json.loads(msg.get("content", "{}"))
                text = content.get("text", "").strip()
                logger.info(f"收到: {text}")

                response = process_message(text)
                if message_id:
                    reply_message(message_id, response)
                    logger.info(f"回复: {response[:30]}...")

    except Exception as e:
        logger.error(f"Error: {e}")


def on_error(ws, error):
    logger.error(f"WS Error: {error}")


def on_close(ws, close_status_code, close_msg):
    logger.warning(f"WS Closed: {close_status_code}")


def on_open(ws):
    logger.info("✓ 飞书 WebSocket 长连接已建立")


def get_ws_connection():
    """Get WebSocket connection info using SDK-style approach"""
    token = get_token()

    # Try to get ws endpoint
    resp = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/ws",
        headers={"Authorization": f"Bearer {token}"},
        json={"AppID": APP_ID, "AppSecret": APP_SECRET},
    )
    logger.info(f"WS endpoint response: {resp.json()}")

    data = resp.json()
    if data.get("code") == 0:
        return data.get("data", {}).get("ws_url")
    return None


def main():
    logger.info("启动飞书双向对话...")

    ws_url = get_ws_connection()
    if not ws_url:
        logger.error("无法获取 WebSocket URL")
        return

    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
    )

    ws.run_forever(ping_interval=30, ping_timeout=10)


if __name__ == "__main__":
    main()
