"""
实验单任务执行器
"""
import time
import logging
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import PatientRecord, AudioSeg, ModelConfig, PatientAsrResult, PatientLlmResult, BUltraResult
from app.models.experiment import ExperimentTask, ExperimentCombination, TaskStatus, TaskStage
from app.config import resolve_hotwords
from app.services.test_executor import TestExecutor
from app.services.parser import evaluate_result, normalize_structured_result

logger = logging.getLogger(__name__)


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
        asr_duration = 0.0
        llm_duration = 0.0
        eval_duration = 0.0

        # Load task
        result = await db.execute(
            select(ExperimentTask).where(ExperimentTask.id == task_id)
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

        # Load LLM model (if configured)
        llm_model = None
        if combo.llm_model_id:
            llm_model = await db.get(ModelConfig, combo.llm_model_id)

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

        # 解析热词
        resolved_hotwords = resolve_hotwords(combo.hotwords, asr_model.params)

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
                asr_start = time.time()
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
                        f"复用 ASR: patient_id={task.patient_id}, "
                        f"record_id={patient.record_id}, "
                        f"asr_model_id={asr_model.id}, "
                        f"result_id={existing_asr_record.id}"
                    )
                else:
                    # 没有成功 ASR, 需要调用
                    logger.info(
                        f"未找到可复用 ASR，开始调用 ASR: "
                        f"patient_id={task.patient_id}, "
                        f"asr_model_id={asr_model.id}"
                    )
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
                        new_asr_record.duration_seconds = round(time.time() - asr_start, 2)
                        asr_result_record = new_asr_record
                        asr_source = "generated"
                        logger.info(
                            f"ASR 调用完成: patient_id={task.patient_id}, "
                            f"result_id={new_asr_record.id}, "
                            f"duration={new_asr_record.duration_seconds}s"
                        )
                    except Exception as e:
                        logger.error(f"Task {task_id} ASR 调用失败: {e}")
                        new_asr_record.status = "failed"
                        new_asr_record.error_message = str(e)
                        asr_duration = round(time.time() - asr_start, 2)
                        # 保存任务快照后再 raise
                        task.asr_result_id = new_asr_record.id
                        task.asr_source = "failed"
                        task.asr_model_name = asr_model.name
                        task.asr_results = []
                        task.full_transcript = ""
                        task.asr_duration = asr_duration
                        task.status = TaskStatus.FAILED.value
                        task.error_type = "asr_failed"
                        task.error_message = str(e)
                        task.completed_at = datetime.utcnow()
                        task.total_duration = round(time.time() - start_time, 2)
                        await db.commit()
                        return {
                            "task_id": task_id,
                            "status": "failed",
                            "asr_source": "failed",
                            "asr_duration": asr_duration,
                            "total_duration": task.total_duration,
                            "error_type": "asr_failed",
                            "error_message": str(e),
                        }

                asr_duration = round(time.time() - asr_start, 2)

                # 任务关联到患者 ASR 记录
                task.asr_result_id = asr_result_record.id
                # 写入快照字段 (保留历史实验可复现)
                task.asr_results = asr_result_record.segments or []
                task.full_transcript = asr_result_record.full_transcript or ""
                task.asr_model_name = asr_model.name
                task.asr_source = asr_source
                task.asr_duration = asr_duration
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
            missing_fields: list[str] = []

            if llm_model and task.stage == TaskStage.LLM.value:
                llm_start = time.time()
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
                        llm_config={
                            "endpoint": llm_model.endpoint,
                            "api_key": llm_model.api_key,
                            "api_secret": llm_model.api_secret,
                            "model_name": llm_model.model_name,
                        },
                        prompt_template=combo.prompt_template,
                    )

                    raw_structured = normalize_structured_result(llm_result["structured_result"])

                    # 校验结构化结果是否包含目标字段
                    target_fields = [
                        "right_follicle_total", "left_follicle_total",
                        "endometrium_thickness", "endometrium_type",
                        "right_ovary_length", "right_ovary_width",
                        "left_ovary_length", "left_ovary_width",
                    ]
                    if raw_structured and isinstance(raw_structured, dict):
                        missing_fields = [f for f in target_fields if f not in raw_structured]
                        if missing_fields:
                            logger.warning(
                                f"Task {task_id}: LLM 返回结构缺少目标字段: {missing_fields}"
                            )

                    llm_result_record.structured_result = raw_structured
                    llm_result_record.summary_text = llm_result["summary_text"]
                    llm_result_record.raw_output = llm_result["llm_raw_output"]
                    llm_result_record.status = "success"

                    # 任务关联
                    task.llm_result_id = llm_result_record.id
                    task.llm_raw_output = llm_result["llm_raw_output"]
                    task.structured_result = raw_structured
                    task.summary_text = llm_result["summary_text"]
                    task.llm_model_name = llm_model.name
                    task.prompt_template_name = combo.prompt_name or ""

                except Exception as e:
                    logger.error(f"Task {task_id} LLM 失败: {e}")
                    task.llm_raw_output = f"[LLM error: {str(e)}]"
                    if llm_result_record:
                        llm_result_record.status = "failed"
                        llm_result_record.error_message = str(e)
                    llm_failed = True

                llm_duration = round(time.time() - llm_start, 2)
                task.llm_duration = llm_duration

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
            if task.structured_result and isinstance(task.structured_result, dict) and not missing_fields:
                eval_start = time.time()
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
                            "right_follicles": gt.right_follicles,
                            "left_follicles": gt.left_follicles,
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
                eval_duration = round(time.time() - eval_start, 2)

            # ============================================================
            # 任务状态判定
            # ============================================================
            if llm_failed:
                task.status = TaskStatus.FAILED.value
                task.error_type = "llm_failed"
                task.error_message = task.llm_raw_output or "LLM 调用失败"
            elif not llm_model:
                # 纯 ASR（未配置 LLM）
                task.status = TaskStatus.SUCCESS.value
                task.stage = TaskStage.ASR.value
            elif llm_model and (not task.structured_result or not isinstance(task.structured_result, dict)):
                task.status = TaskStatus.FAILED.value
                task.error_type = "empty_structured_result"
                task.error_message = "LLM 未返回可用结构化结果"
            elif missing_fields:
                task.status = TaskStatus.FAILED.value
                task.error_type = "invalid_structured_schema"
                task.error_message = f"LLM 返回结构缺少目标字段: {', '.join(missing_fields)}"
            else:
                task.status = TaskStatus.SUCCESS.value
                task.stage = TaskStage.LLM.value

            task.completed_at = datetime.utcnow()

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            task.status = TaskStatus.FAILED.value
            if not task.error_type:
                task.error_type = self._categorize_error(e)
            if not task.error_message:
                task.error_message = str(e)

        total_duration = round(time.time() - start_time, 2)
        task.total_duration = total_duration
        await db.commit()

        # 汇总日志
        logger.info(
            f"Task {task_id} 完成: status={task.status}, "
            f"ASR source={asr_source or 'n/a'}, "
            f"ASR duration={asr_duration}s, "
            f"LLM duration={llm_duration}s, "
            f"Eval duration={eval_duration}s, "
            f"Total duration={total_duration}s"
        )

        return {
            "task_id": task_id,
            "status": task.status,
            "asr_source": asr_source,
            "asr_duration": asr_duration,
            "llm_duration": llm_duration,
            "eval_duration": eval_duration,
            "duration": total_duration,
            "error_type": task.error_type,
        }

    @staticmethod
    def _categorize_error(error: Exception) -> str:
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
