"""
实验单任务执行器
"""
import time
from datetime import datetime
import uuid
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import PatientRecord, AudioSeg, ModelConfig, PatientAsrResult, PatientLlmResult
from app.models.experiment import ExperimentTask, ExperimentCombination, BatchStatus, TaskStatus, TaskStage
from app.config import resolve_hotwords
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

        # Load patient with segs / result / date_folder
        patient_result = await db.execute(
            select(PatientRecord)
            .options(
                selectinload(PatientRecord.segs),
                selectinload(PatientRecord.result),
                selectinload(PatientRecord.date_folder),
            )
            .where(PatientRecord.id == task.patient_id)
        )
        patient = patient_result.scalar_one_or_none()
        if not patient:
            raise ValueError(f"Patient {task.patient_id} not found")

        # 提前取出 date_str, 避免后续隐式懒加载
        date_str = patient.date_folder.date if patient.date_folder else None

        # Load ASR model
        asr_model = await db.get(ModelConfig, combo.asr_model_id)
        if not asr_model:
            raise ValueError(f"ASR model {combo.asr_model_id} not found")

        segs = [
            {"seg_index": s.seg_index, "file_path": s.file_path, "duration": s.duration}
            for s in sorted(patient.segs, key=lambda x: x.seg_index)
        ]

        executor = TestExecutor()
        asr_config = {
            "endpoint": asr_model.endpoint,
            "api_key": asr_model.api_key,
            "api_secret": asr_model.api_secret,
            "model_name": asr_model.model_name,
            "hotwords": combo.hotwords,
        }

        # 解析热词 (使用 resolve_hotwords 保持优先级接口 > 模型配置 > 默认)
        resolved_hotwords = resolve_hotwords(combo.hotwords, asr_model.params)

        llm_config = None
        llm_model = None
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
            if not segs:
                raise ValueError(f"Patient {task.patient_id} has no audio segments")
            # Determine if ASR needs to run
            run_asr = task.stage == TaskStage.ASR.value or not task.full_transcript

            asr_result_record = None
            if run_asr:
                # 创建患者级 ASR 记录
                asr_result_record = PatientAsrResult(
                    patient_id=task.patient_id,
                    record_id=patient.record_id,
                    date=date_str,
                    asr_model_id=asr_model.id,
                    asr_model_name=asr_model.name,
                    provider=asr_model.provider,
                    hotwords=resolved_hotwords or [],
                    status="running",
                )
                db.add(asr_result_record)
                await db.flush()  # 获得 id

                asr_result = await executor.execute_asr(
                    segs=segs,
                    asr_provider=asr_model.provider,
                    asr_config=asr_config,
                    hotwords=resolved_hotwords,
                )
                # 写入患者级 ASR 记录
                asr_result_record.segments = asr_result["asr_results"]
                asr_result_record.full_transcript = asr_result["full_transcript"]
                asr_result_record.status = "success"
                asr_result_record.duration_seconds = 0  # TODO: track via executor

                # 任务关联到患者 ASR 记录
                task.asr_result_id = asr_result_record.id

                # 写入快照字段 (保留历史实验可复现)
                task.asr_results = asr_result["asr_results"]
                task.full_transcript = asr_result["full_transcript"]
                task.stage = TaskStage.LLM.value

            # 把最新 ASR 设为当前 (同 patient 其他设 False)
            if asr_result_record:
                await db.execute(
                    update(PatientAsrResult)
                    .where(
                        PatientAsrResult.patient_id == task.patient_id,
                        PatientAsrResult.id != asr_result_record.id,
                    )
                    .values(is_current=False)
                )
                await db.execute(
                    update(PatientAsrResult)
                    .where(PatientAsrResult.id == asr_result_record.id)
                    .values(is_current=True)
                )

            # Run LLM if configured
            llm_result_record = None
            if llm_config and task.stage == TaskStage.LLM.value and llm_model:
                try:
                    # 创建患者级 LLM 记录
                    llm_result_record = PatientLlmResult(
                        patient_id=task.patient_id,
                        asr_result_id=task.asr_result_id,
                        llm_model_id=llm_model.id,
                        llm_model_name=llm_model.name,
                        prompt_content=combo.prompt_template,
                        prompt_version="v1.0",
                        status="running",
                    )
                    db.add(llm_result_record)
                    await db.flush()

                    llm_result = await executor.execute_llm(
                        transcript=task.full_transcript,
                        llm_provider=llm_model.provider,
                        llm_config=llm_config,
                        prompt_template=combo.prompt_template,
                    )

                    # 写入患者级 LLM 记录
                    llm_result_record.structured_result = llm_result["structured_result"]
                    llm_result_record.summary_text = llm_result["summary_text"]
                    llm_result_record.raw_output = llm_result["llm_raw_output"]
                    llm_result_record.status = "success"

                    # 任务关联
                    task.llm_result_id = llm_result_record.id

                    # 快照字段
                    task.llm_raw_output = llm_result["llm_raw_output"]
                    task.structured_result = llm_result["structured_result"]
                    task.summary_text = llm_result["summary_text"]
                    task.llm_duration = 0
                except Exception as e:
                    logger.error(f"LLM failed for task {task_id}: {e}")
                    task.llm_raw_output = f"[LLM error: {str(e)}]"
                    if llm_result_record:
                        llm_result_record.status = "failed"
                        llm_result_record.error_message = str(e)

            # 把最新 LLM 设为当前
            if llm_result_record and llm_result_record.status == "success":
                await db.execute(
                    update(PatientLlmResult)
                    .where(
                        PatientLlmResult.patient_id == task.patient_id,
                        PatientLlmResult.id != llm_result_record.id,
                    )
                    .values(is_current=False)
                )
                await db.execute(
                    update(PatientLlmResult)
                    .where(PatientLlmResult.id == llm_result_record.id)
                    .values(is_current=True)
                )

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
                            "remark": gt.remark,
                        }
                    )
                    task.evaluation = evaluation
                    task.accuracy = evaluation.get("accuracy")

            task.status = TaskStatus.SUCCESS.value
            task.stage = TaskStage.LLM.value
            task.completed_at = datetime.utcnow()

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
