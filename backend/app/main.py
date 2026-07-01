"""
应用入口 - 供 uvicorn 使用
"""
from app import app

if __name__ == "__main__":
    import uvicorn
    from app.config import settings
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT)
