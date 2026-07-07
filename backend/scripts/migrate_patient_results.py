"""
幂等迁移：
1. 为 experiment_tasks 添加 asr_result_id / llm_result_id 字段
2. 创建 patient_asr_results / patient_llm_results 表

使用方式：python -m scripts.migrate_patient_results
"""
import asyncio
from sqlalchemy import text
from app.database import engine, Base
from app.models import PatientAsrResult, PatientLlmResult  # 确保模型被注册


async def main():
    async with engine.begin() as conn:
        # 1. 创建新表 (幂等, create_all 会跳过已存在的表)
        await conn.run_sync(Base.metadata.create_all)

        # 2. 检查并补 experiment_tasks 缺失的列
        result = await conn.execute(text("PRAGMA table_info(experiment_tasks)"))
        existing_columns = {row[1] for row in result.fetchall()}

        if "asr_result_id" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE experiment_tasks ADD COLUMN asr_result_id INTEGER")
            )
            print("[ok] 已添加 asr_result_id 到 experiment_tasks")
        else:
            print("[skip] asr_result_id 已存在")

        if "llm_result_id" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE experiment_tasks ADD COLUMN llm_result_id INTEGER")
            )
            print("[ok] 已添加 llm_result_id 到 experiment_tasks")
        else:
            print("[skip] llm_result_id 已存在")

    print("[done] 迁移完成")


if __name__ == "__main__":
    asyncio.run(main())
