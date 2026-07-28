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
            await _ensure_column(conn, "patient_asr_results", "source", "VARCHAR(50) DEFAULT 'normal'")
            await _ensure_column(conn, "patient_asr_results", "experiment_key", "VARCHAR(100)")
            await _ensure_column(conn, "patient_asr_results", "config_hash", "VARCHAR(64)")
            await _ensure_column(conn, "patient_asr_results", "config_snapshot", "JSON")
            await _ensure_column(conn, "patient_llm_results", "source", "VARCHAR(50) DEFAULT 'normal'")
            await _ensure_column(conn, "patient_llm_results", "experiment_key", "VARCHAR(100)")
            await _ensure_column(conn, "asr_optimization_plans", "source", "VARCHAR(30) DEFAULT 'custom'")
            await _ensure_column(conn, "asr_reference_transcripts", "reference_annotations", "JSON")
            # ASR 转化评估新增字段
            await _ensure_column(conn, "asr_conversion_records", "warnings", "TEXT")
            await _ensure_column(conn, "asr_conversion_records", "risk_passed", "INTEGER DEFAULT 1")
            await _ensure_column(conn, "asr_conversion_records", "risk_blocked", "INTEGER DEFAULT 0")
            await _ensure_column(conn, "asr_conversion_records", "fields_snapshot", "JSON")
            await _ensure_column(conn, "asr_conversion_records", "batch_id", "INTEGER")
            await _ensure_column(conn, "asr_conversion_records", "status", "VARCHAR(30) DEFAULT 'ready'")
            await _ensure_column(conn, "asr_conversion_records", "error_message", "TEXT")
            await _ensure_column(conn, "asr_conversion_batches", "success_count", "INTEGER DEFAULT 0")
            await _ensure_column(conn, "asr_conversion_batches", "failed_count", "INTEGER DEFAULT 0")
            await conn.execute(text(
                "UPDATE asr_conversion_records SET status = 'ready' "
                "WHERE status IS NULL OR status = ''"
            ))
            await conn.execute(text(
                "UPDATE asr_conversion_batches SET "
                "record_count = (SELECT COUNT(*) FROM asr_conversion_records r WHERE r.batch_id = asr_conversion_batches.id), "
                "success_count = (SELECT COUNT(*) FROM asr_conversion_records r WHERE r.batch_id = asr_conversion_batches.id AND COALESCE(r.status, 'ready') != 'failed'), "
                "failed_count = (SELECT COUNT(*) FROM asr_conversion_records r WHERE r.batch_id = asr_conversion_batches.id AND r.status = 'failed')"
            ))


async def _ensure_column(conn, table: str, column: str, ddl: str):
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    columns = {row[1] for row in result.fetchall()}
    if column not in columns:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


async def execute_write(statement):
    """Utility to write to DB safely"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(statement)
        await session.commit()
        return result
