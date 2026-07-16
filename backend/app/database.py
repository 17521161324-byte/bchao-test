"""
数据库连接与会话管理
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.config import settings
import asyncio
from pathlib import Path


# 转换 SQLite URL 为异步格式
def _get_db_url():
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        db_path = url.replace("sqlite:///", "", 1)
        # 相对路径必须固定到 backend 目录，避免从 C:\Windows\system32 或其他目录
        # 启动 uvicorn 时创建/连接到一套空数据库。
        if db_path and not Path(db_path).is_absolute():
            backend_dir = Path(__file__).resolve().parents[1]
            db_path = str((backend_dir / db_path).resolve())
        url = f"sqlite+aiosqlite:///{db_path}"
    return url


engine = create_async_engine(
    _get_db_url(),
    echo=settings.APP_ENV == "development",
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """初始化数据库表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if _get_db_url().startswith("sqlite+aiosqlite:///"):
            result = await conn.execute(text("PRAGMA table_info(patient_records)"))
            columns = {row[1] for row in result.fetchall()}
            if "note" not in columns:
                await conn.execute(text("ALTER TABLE patient_records ADD COLUMN note TEXT"))


async def execute_write(statement):
    """Utility to write to DB safely"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        await session.commit()
        return result
