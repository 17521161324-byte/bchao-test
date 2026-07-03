"""
B 超语音测试平台 - FastAPI 应用入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from loguru import logger

from app.config import settings
from app.database import init_db
from app.routers import audio, result, model_config, test, experiment


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info(f"🚀 {settings.APP_NAME} 启动中...")
    await init_db()
    logger.info("✅ 数据库初始化完成")
    yield
    logger.info("👋 应用关闭")


app = FastAPI(
    title="B 超语音测试平台",
    description="辅助生殖 B 超语音识别测试平台 API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(audio.router, prefix="/api/audio", tags=["录音管理"])
app.include_router(result.router, prefix="/api/result", tags=["结果管理"])
app.include_router(model_config.router, prefix="/api/model", tags=["模型配置"])
app.include_router(test.router, prefix="/api/test", tags=["测试执行"])
app.include_router(experiment.router, prefix="/api/experiments", tags=["批量实验"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME}


# 静态文件（前端构建产物）
import os
_static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(_static_dir, "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(_static_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_static_dir, "index.html"))
