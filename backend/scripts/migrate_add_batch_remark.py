"""
幂等迁移：为 experiment_batches 添加 remark 字段
"""
import asyncio
from sqlalchemy import text
from app.database import engine


async def main():
    async with engine.begin() as conn:
        try:
            await conn.execute(
                text("ALTER TABLE experiment_batches ADD COLUMN remark TEXT DEFAULT ''")
            )
            print("✅ 已添加 remark 字段到 experiment_batches")
        except Exception as e:
            msg = str(e).lower()
            if "duplicate column" in msg or "already exists" in msg:
                print("ℹ️  remark 字段已存在，跳过")
            else:
                raise


if __name__ == "__main__":
    asyncio.run(main())
