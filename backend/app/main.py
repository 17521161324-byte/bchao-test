"""
应用入口 - 供 uvicorn 使用
"""
import asyncio

# Windows 平台需要使用 Selector 事件循环以兼容 aiosqlite/greenlet
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app import app

if __name__ == "__main__":
    import uvicorn
    from app.config import settings
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT)
