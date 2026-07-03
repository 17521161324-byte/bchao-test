"""
实验单任务执行器
"""
import time
import uuid
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PatientRecord, AudioSeg, ModelConfig
from app.models.experiment import ExperimentTask, ExperimentCombination, BatchStatus, TaskStatus, TaskStage
from app.services.test_executor import TestExecutor
from app.services.parser import evaluate_result


class ExperimentRunner:
    """执行单个实验任务，支持 ASR 复用"""

    async def run(self, db: AsyncSession, task_id: int) -> dict:
        """
        执行单个实验任务。

        Returns:
            dict with execution result summary
        """
        start_time = time.time()

        # Load task with relationships
        result = await db.execute(
            select(ExperimentTask)
            .where(ExperimentTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Load combination
        combo = await db.get(ExperimentCombination, task.combination_id)
        if not combo:
            raise ValueError(f"Combination {task.combination_id} not found")

        # Load patient with segs
        patient_result = await db.execute(
            select(PatientRecord)
            .options(selectinload(PatientRecord))
            .where(PatientRecord.id == task.patient_id)
        )
        patient = patient_result.scalar_one_or_none()
        if not patient:
            raise ValueError(f"Patient {task.patient_id} not found")

        # Load ASR model
        asr_model = await db.get(ModelConfig, combo.asr_model_id)
        if not asr_model:
            raise ValueError(f"ASR model {combo.asr_model_id} not found")

        segs = [
            {"seg_index": s.seg_index, "file_path": s.file_path, "duration": s.duration}
            for s in sorted(patient.segs, key=lambda x: x.seg_index)
        ]

        if not segs:
            raise ValueError(f"Patient {task.record_id} has no audio segments")

        executor = TestExecutor()
        asr_config = {
            "endpoint": asr_model.endpoint,
            "api_key": asr_model.api_key,
            "api_secret": asr_model.api_secret,
            "model_name": asr_model.model_name,
            "hotwords": combo.hotwords,
        }

        llm_config = None
        if combo.llm_model_id:
            llm_model = await db.get(ModelConfig, combo.llm_model_id)
            if llm_model:
                llm_config = {
                    "endpoint": llm_model.endpoint,
                    "api_key": llm_model.api_key,
                    "api_secret": llm_model.api_secret,
                    "model_name": llm_model.model_name,
                }

        try:
            # Determine if ASR needs to run
            run_asr = task.stage == TaskStage.ASR.value or not task.full_transcript

            if run_asr:
                asr_result = await executor.execute_asr(
                    segs=segs,
                    asr_provider=asr_model.provider,
                    asr_config=asr_config,
                )
                task.asr_results = asr_result["asr_results"]
                task.full_transcript = asr_result["full_transcript"]
                task.stage = TaskStage.LLM.value

            # Run LLM if configured
            if llm_config and task.stage == TaskStage.LLM.value:
                try:
                    llm_result = await executor.execute_llm(
                        transcript=task.full_transcript,
                        llm_provider=llm_model.provider,
                        llm_config=llm_config,
                        prompt_template=combo.prompt_template,
                    )
                    task.llm_raw_output = llm_result["llm_raw_output"]
                    task.structured_result = llm_result["structured_result"]
                    task.summary_text = llm_result["summary_text"]
                    task.llm_duration = 0  # Would track actual duration
                except Exception as e:
                    logger.error(f"LLM failed for task {task_id}: {e}")
                    task.llm_raw_output = f"[LLM error: {str(e)}]"

            # Evaluate if we have structured result
            if task.structured_result:
                from app.models import BUltraResult
                gt_result = await db.execute(
                    select(BUltraResult).where(BUltraResult.patient_id == task.patient_id)
                )
                gt = gt_result.scalar_one_or_none()
                if gt:
                    evaluation = evaluate_result(
                        identified=task.structured_result,
                        ground_truth={
                            "right_follicle_total": gt.right_follicle_total,
                            "left_follicle_total": gt.left_follicle_total,
                            "endometrium_thickness": gt.endometrium_thickness,
                            "endometrium_type": gt.endometrium_type,
                            "right_ovary_length": gt.right_ovary_length,
                            "right_ovary_width": gt.right_ovary_width,
                            "left_ovary_length": gt.left_ovary_length,
                            "left_ovary_width": gt.left_ovary_width,
                        }
                    )
                    task.evaluation = evaluation
                    task.accuracy = evaluation.get("accuracy")

            task.status = TaskStatus.SUCCESS.value
            task.stage = TaskStage.LLM.value
            task.completed_at = time.time()

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            task.status = TaskStatus.FAILED.value
            task.error_type = self._categorize_error(e)
            task.error_message = str(e)

        task.total_duration = round(time.time() - start_time, 2)
        await db.commit()

        return {
            "task_id": task_id,
            "status": task.status,
            "duration": task.total_duration,
            "error_type": task.error_type,
        }

    def _categorize_error(self, error: Exception) -> str:
        """Categorize exception type"""
        error_msg = str(error).lower()
        if "timeout" in error_msg:
            return "model_timeout"
        if "audio" in error_msg or "file" in error_msg:
            return "missing_audio"
        if "format" in error_msg or "json" in error_msg:
            return "invalid_response"
        if "quota" in error_msg or "rate" in error_msg:
            return "quota"
        return "unknown"
