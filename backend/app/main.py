"""
应用入口 - 供 uvicorn 使用
"""
import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def create_app():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse
    from contextlib import asynccontextmanager
    from loguru import logger

    from app.config import settings
    from app.database import init_db
    from app.routers import audio, result, model_config, test, experiment, prompt_template, patients, field_review

    _worker = None
    _worker_task = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _worker, _worker_task
        logger.info(f"🚀 {settings.APP_NAME} 启动中...")
        await init_db()
        logger.info("✅ 数据库初始化完成")

        # 启动后台任务 Worker
        try:
            from app.workers.experiment_worker import ExperimentWorker
            _worker = ExperimentWorker(poll_interval=2.0)
            loop = asyncio.get_event_loop()
            _worker_task = loop.create_task(_worker.start())
            logger.info("✅ 实验任务 Worker 已启动")
        except Exception as e:
            logger.warning(f"⚠️ Worker 启动失败（非关键）: {e}")

        yield

        if _worker:
            _worker.stop()
        if _worker_task:
            try:
                _worker_task.cancel()
            except Exception:
                pass
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
    app.include_router(prompt_template.router, prefix="/api/prompt-templates", tags=["提示词模版"])
    app.include_router(patients.router, prefix="/api/patients", tags=["患者结果"])
    app.include_router(field_review.router, prefix="/api/patients", tags=["字段标记"])

    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "app": settings.APP_NAME}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    from app.config import settings
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT)
