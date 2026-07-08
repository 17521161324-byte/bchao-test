"""
迁移: 为 experiment_tasks 补充快照字段

新增字段:
- asr_source: reused / generated / failed / missing
- asr_model_name: 冗余快照
- llm_model_name: 冗余快照
- prompt_template_name: 冗余快照

使用方式: python -m scripts.migrate_experiment_task_fields
"""
import asyncio
from sqlalchemy import text
from app.database import engine


async def main():
    async with engine.begin() as conn:
        # 检查现有列
        result = await conn.execute(text("PRAGMA table_info(experiment_tasks)"))
        existing_columns = {row[1] for row in result.fetchall()}

        new_columns = [
            ("asr_source", "VARCHAR(20)"),
            ("asr_model_name", "VARCHAR(100)"),
            ("llm_model_name", "VARCHAR(100)"),
            ("prompt_template_name", "VARCHAR(100)"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                await conn.execute(
                    text(f"ALTER TABLE experiment_tasks ADD COLUMN {col_name} {col_type}")
                )
                print(f"[ok] 已添加 {col_name}")
            else:
                print(f"[skip] {col_name} 已存在")

    print("[done] 迁移完成")


if __name__ == "__main__":
    asyncio.run(main())
