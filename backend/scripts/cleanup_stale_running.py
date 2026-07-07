"""
清理卡住的 running 任务记录 (patient_asr_results / patient_llm_results)

由于旧版本代码中 ASR 执行失败时未正确设置 status=failed,
可能导致记录永久停留在 running 状态。此脚本清理这些记录。

使用方式: python -m scripts.cleanup_stale_running
"""
import asyncio
from sqlalchemy import text
from app.database import engine


async def main():
    async with engine.begin() as conn:
        # 清理超过 1 分钟的 running 记录 (认为是卡住)
        result = await conn.execute(
            text(
                "UPDATE patient_asr_results "
                "SET status='failed', error_message='任务被清理:旧版本未完成或进程重启' "
                "WHERE status='running' AND "
                "strftime('%s','now') - strftime('%s', created_at) > 60"
            )
        )
        print(f"[ok] patient_asr_results 清理 {result.rowcount} 条卡住记录")

        result2 = await conn.execute(
            text(
                "UPDATE patient_llm_results "
                "SET status='failed', error_message='任务被清理:旧版本未完成或进程重启' "
                "WHERE status='running' AND "
                "strftime('%s','now') - strftime('%s', created_at) > 60"
            )
        )
        print(f"[ok] patient_llm_results 清理 {result2.rowcount} 条卡住记录")

    print("[done]")


if __name__ == "__main__":
    asyncio.run(main())
