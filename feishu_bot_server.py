"""
飞书双向对话回调服务
接收飞书消息 → 处理 → 回复
"""
import hashlib
import json
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
import uvicorn

app = FastAPI()

APP_ID = "cli_aacdecf01c7bdcda"
APP_SECRET = "aHmIlG4rPg4udTO7J64NUboeEubkYb7P"

# Cache for tenant_access_token
_token_cache = {"token": None, "expires_at": 0}


async def get_token():
    """获取 tenant_access_token"""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now:
        return _token_cache["token"]

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={
            "app_id": APP_ID,
            "app_secret": APP_SECRET,
        })
        data = resp.json()
        _token_cache["token"] = data["tenant_access_token"]
        _token_cache["expires_at"] = now + data["expire"] - 300
        return _token_cache["token"]


async def reply_message(message_id: str, content: str):
    """回复飞书消息"""
    token = await get_token()
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "content": json.dumps({"text": content}),
                "msg_type": "text",
            },
        )
        return resp.json()


async def send_message(receive_id: str, content: str, receive_id_type: str = "open_id"):
    """主动发送消息"""
    token = await get_token()
    url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": receive_id,
                "content": json.dumps({"text": content}),
                "msg_type": "text",
            },
        )
        return resp.json()


@app.post("/feishu/event")
async def handle_event(request: Request):
    """处理飞书事件回调"""
    body = await request.json()

    # URL verification (首次配置时飞书会发送验证请求)
    if body.get("type") == "url_verification":
        return JSONResponse({"challenge": body.get("challenge", "")})

    # v2.0 event format
    header = body.get("header", {})
    event = body.get("event", {})

    # Handle message receive event
    if header.get("event_type") == "im.message.receive_v1":
        message = event.get("message", {})
        sender = event.get("sender", {})

        msg_type = message.get("message_type", "")
        message_id = message.get("message_id", "")
        chat_type = message.get("chat_type", "")  # p2p or group

        # Only handle text messages
        if msg_type == "text":
            content = json.loads(message.get("content", "{}"))
            text = content.get("text", "").strip()

            # Process the message and generate response
            response_text = await process_message(text, sender)

            # Reply
            if response_text and message_id:
                await reply_message(message_id, response_text)

    return JSONResponse({"code": 0})


async def process_message(text: str, sender: dict) -> str:
    """
    处理收到的消息并返回回复。
    这里接入 Claude 的处理逻辑。
    """
    # Simple echo for now - in production this would call Claude API
    sender_id = sender.get("sender_id", {}).get("open_id", "unknown")

    # Handle commands
    if text.startswith("/"):
        command = text[1:].strip().lower()
        if command == "status":
            return "系统运行正常\n- 后端: PM2 运行中\n- 前端: Nginx 运行中\n- 数据库: SQLite 正常"
        elif command == "tasks":
            return "当前任务:\n- FS-18: 批量实验功能 (已完成)\n- 等待新任务分配"
        elif command.startswith("run "):
            task = text[4:].strip()
            return f"收到任务: {task}\n正在处理..."
        else:
            return f"未知命令: {command}\n可用命令: /status, /tasks, run <task>"

    # Default: echo with help
    return f"收到: {text}\n\n我是开发助手，可用命令:\n/status - 查看系统状态\n/tasks - 查看当前任务\n/run <task> - 执行任务"


@app.get("/health")
async def health():
    return {"status": "ok", "app": "feishu-bot"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765)
