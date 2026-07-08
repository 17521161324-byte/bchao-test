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

        核心逻辑:
        1. ASR 阶段: 优先复用 patient_asr_results 中同一 patient+model 的成功结果
        2. LLM 阶段: 使用快照 full_transcript 调用 LLM
        3. 评估阶段: 与 BUltraResult 真实值对比
        4. 任务快照: 保存 asr_source/asr_model_name/llm_model_name/prompt_template_name

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

            # ============================================================
            # 阶段 1: ASR (优先复用已有成功结果)
            # ============================================================
            run_asr = task.stage == TaskStage.ASR.value or not task.full_transcript
            asr_result_record = None
            asr_source = None  # reused / generated / failed

            if run_asr:
                # 查询同一 patient + asr_model 的已有成功记录
                existing_asr = await db.execute(
                    select(PatientAsrResult)
                    .where(
                        PatientAsrResult.patient_id == task.patient_id,
                        PatientAsrResult.asr_model_id == asr_model.id,
                        PatientAsrResult.status == "success",
                    )
                    .order_by(PatientAsrResult.created_at.desc())
                    .limit(1)
                )
                existing_asr_record = existing_asr.scalar_one_or_none()

                if existing_asr_record and existing_asr_record.full_transcript:
                    # 复用已有成功 ASR
                    asr_result_record = existing_asr_record
                    asr_source = "reused"
                    logger.info(
                        f"Task {task_id}: 复用 ASR result {existing_asr_record.id} "
                        f"(model={asr_model.name}, patient={task.patient_id})"
                    )
                else:
                    # 没有成功 ASR, 需要调用
                    new_asr_record = PatientAsrResult(
                        patient_id=task.patient_id,
                        record_id=patient.record_id,
                        date=date_str,
                        asr_model_id=asr_model.id,
                        asr_model_name=asr_model.name,
                        provider=asr_model.provider,
                        hotwords=resolved_hotwords or [],
                        status="running",
                    )
                    db.add(new_asr_record)
                    await db.flush()  # 获得 id

                    try:
                        asr_result = await executor.execute_asr(
                            segs=segs,
                            asr_provider=asr_model.provider,
                            asr_config=asr_config,
                            hotwords=resolved_hotwords,
                        )
                        new_asr_record.segments = asr_result["asr_results"]
                        new_asr_record.full_transcript = asr_result["full_transcript"]
                        new_asr_record.status = "success"
                        new_asr_record.duration_seconds = 0
                        asr_result_record = new_asr_record
                        asr_source = "generated"
                    except Exception as e:
                        logger.error(f"Task {task_id} ASR 调用失败: {e}")
                        new_asr_record.status = "failed"
                        new_asr_record.error_message = str(e)
                        # 保存任务快照后再 raise, 确保失败状态持久化
                        task.asr_result_id = new_asr_record.id
                        task.asr_source = "failed"
                        task.asr_model_name = asr_model.name
                        task.asr_results = []
                        task.full_transcript = ""
                        task.status = TaskStatus.FAILED.value
                        task.error_type = "asr_failed"
                        task.error_message = str(e)
                        task.completed_at = datetime.utcnow()
                        raise  # 向上传递, 统一在 finally 或无异常路径外捕获

                # 任务关联到患者 ASR 记录
                task.asr_result_id = asr_result_record.id
                # 写入快照字段 (保留历史实验可复现)
                task.asr_results = asr_result_record.segments or []
                task.full_transcript = asr_result_record.full_transcript or ""
                task.asr_model_name = asr_model.name
                task.asr_source = asr_source
                task.stage = TaskStage.LLM.value

                # 把最新 ASR 设为当前 (同 patient 其他设 False)
                if asr_result_record.status == "success":
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

            # ============================================================
            # 阶段 2: LLM 结构化提取
            # ============================================================
            llm_result_record = None
            llm_failed = False

            if llm_config and task.stage == TaskStage.LLM.value and llm_model:
                try:
                    # 创建患者级 LLM 记录
                    llm_result_record = PatientLlmResult(
                        patient_id=task.patient_id,
                        asr_result_id=task.asr_result_id,
                        llm_model_id=llm_model.id,
                        llm_model_name=llm_model.name,
                        prompt_template_name=combo.prompt_name or None,
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
                    task.llm_model_name = llm_model.name
                    task.prompt_template_name = combo.prompt_name or ""
                    task.llm_duration = 0

                except Exception as e:
                    logger.error(f"Task {task_id} LLM 失败: {e}")
                    task.llm_raw_output = f"[LLM error: {str(e)}]"
                    if llm_result_record:
                        llm_result_record.status = "failed"
                        llm_result_record.error_message = str(e)
                    llm_failed = True

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

            # ============================================================
            # 阶段 3: 评估
            # ============================================================
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

            # ============================================================
            # 任务状态判定
            # ============================================================
            # LLM 失败 → 任务失败
            if llm_failed:
                task.status = TaskStatus.FAILED.value
                task.error_type = "llm_failed"
                task.error_message = task.llm_raw_output or "LLM 调用失败"
            # 没有配置 LLM (纯 ASR)
            elif not llm_config:
                task.status = TaskStatus.SUCCESS.value
                task.stage = TaskStage.ASR.value  # 只完成 ASR
            # 有 LLM 但 structured_result 为空
            elif llm_config and not task.structured_result:
                task.status = TaskStatus.FAILED.value
                task.error_type = "empty_structured_result"
                task.error_message = "LLM 未返回可用结构化结果"
            else:
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
