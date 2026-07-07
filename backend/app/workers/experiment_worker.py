"""
实验 Worker - 单并发任务领取与执行
"""
import asyncio
import time
import uuid
from datetime import datetime, timedelta
from loguru import logger
from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.experiment import ExperimentBatch, ExperimentTask, BatchStatus, TaskStatus
from app.services.experiment_runner import ExperimentRunner


class ExperimentWorker:
    """单 Worker 从数据库领取并执行任务"""

    def __init__(self, poll_interval: float = 1.0):
        self.poll_interval = poll_interval
        self.worker_id = str(uuid.uuid4())[:8]
        self._running = False

    async def start(self):
        """启动 Worker 主循环"""
        self._running = True
        logger.info(f"Worker {self.worker_id} started")

        await self.recover_expired_leases()

        while self._running:
            try:
                worked = await self.process_one()
                if not worked:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}")
                await asyncio.sleep(self.poll_interval)

    async def stop(self):
        """停止 Worker"""
        self._running = False

    async def recover_expired_leases(self):
        """恢复过期的租约"""
        async with AsyncSessionLocal() as db:
            cutoff = datetime.utcnow() - timedelta(minutes=5)
            result = await db.execute(
                select(ExperimentTask).where(
                    ExperimentTask.status == TaskStatus.RUNNING.value,
                    ExperimentTask.lease_expires_at < cutoff,
                )
            )
            expired = result.scalars().all()
            for task in expired:
                task.status = TaskStatus.PENDING.value
                task.worker_id = None
                task.lease_expires_at = None
            await db.commit()
            if expired:
                logger.info(f"Recovered {len(expired)} expired leases")

    async def process_one(self) -> bool:
        """处理一个任务，返回是否找到并执行了任务"""
        async with AsyncSessionLocal() as db:
            # Find oldest pending task from running batch
            result = await db.execute(
                select(ExperimentTask)
                .join(ExperimentBatch, ExperimentTask.batch_id == ExperimentBatch.id)
                .where(
                    ExperimentBatch.status == BatchStatus.RUNNING.value,
                    ExperimentTask.status == TaskStatus.PENDING.value,
                )
                .order_by(ExperimentTask.created_at)
                .limit(1)
            )
            task = result.scalar_one_or_none()

            if not task:
                return False

            # Claim task
            task.status = TaskStatus.RUNNING.value
            task.worker_id = self.worker_id
            task.lease_expires_at = datetime.utcnow() + timedelta(minutes=2)
            task.started_at = datetime.utcnow()
            await db.commit()

            task_id = task.id

        # Execute outside DB session (long operation)
        try:
            async with AsyncSessionLocal() as run_db:
                runner = ExperimentRunner()
                await runner.run(run_db, task_id)

            # Update batch counters
            async with AsyncSessionLocal() as db:
                task = await db.get(ExperimentTask, task_id)
                batch = await db.get(ExperimentBatch, task.batch_id)

                if task.status == TaskStatus.SUCCESS.value:
                    batch.success_count += 1
                elif task.status == TaskStatus.FAILED.value:
                    batch.failure_count += 1

                # Check if batch is complete
                if batch.success_count + batch.failure_count >= batch.total_tasks:
                    if batch.failure_count == 0:
                        batch.status = BatchStatus.COMPLETED.value
                    else:
                        batch.status = BatchStatus.PARTIAL.value

                await db.commit()

        except Exception as e:
            logger.error(f"Task {task_id} execution failed: {e}")
            async with AsyncSessionLocal() as db:
                task = await db.get(ExperimentTask, task_id)
                task.status = TaskStatus.FAILED.value
                task.error_message = str(e)
                await db.commit()

        return True

    async def heartbeat(self, db, task_id: int):
        """Update lease expiry for long-running task"""
        await db.execute(
            update(ExperimentTask)
            .where(ExperimentTask.id == task_id)
            .values(lease_expires_at=datetime.utcnow() + timedelta(minutes=2))
        )
        await db.commit()


async def main():
    """Entry point for running the worker"""
    worker = ExperimentWorker(poll_interval=1.0)
    try:
        await worker.start()
    except KeyboardInterrupt:
        await worker.stop()
        logger.info(f"Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
