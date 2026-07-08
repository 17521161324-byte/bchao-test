"""
迁移: 为 patient_llm_results 添加 prompt_template_id / prompt_template_name

使用方式: python -m scripts.migrate_add_llm_prompt_fields
"""
import asyncio
from sqlalchemy import text
from app.database import engine


async def main():
    async with engine.begin() as conn:
        # 检查列是否存在
        result = await conn.execute(text("PRAGMA table_info(patient_llm_results)"))
        existing_columns = {row[1] for row in result.fetchall()}

        if "prompt_template_id" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE patient_llm_results ADD COLUMN prompt_template_id INTEGER")
            )
            print("[ok] 已添加 prompt_template_id 列")
        else:
            print("[skip] prompt_template_id 已存在")

        if "prompt_template_name" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE patient_llm_results ADD COLUMN prompt_template_name VARCHAR(100)")
            )
            print("[ok] 已添加 prompt_template_name 列")
        else:
            print("[skip] prompt_template_name 已存在")

    print("[done] 迁移完成")


if __name__ == "__main__":
    asyncio.run(main())
