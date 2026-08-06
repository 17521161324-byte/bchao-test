"""ASR text validation API."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    BUltraResult,
    ConversionConfigVersion,
    ModelConfig,
    PatientAsrResult,
    PatientRecord,
    PromptTemplate,
    TextCorrectionTemplate,
    TextValidationRun,
)
from app.schemas.text_validation import (
    TextCorrectionTemplateCreate,
    TextCorrectionTemplateOut,
    TextCorrectionTemplateUpdate,
    TextValidationRunCreate,
    TextValidationRunOut,
)
from app.services.conversion_engine import run_conversion
from app.services.conversion_engine.business_segment_locator import locate_business_segments
from app.services.conversion_config import load_enabled_lexicon_rules, load_enabled_runtime_rules
from app.services.llm import create_llm
from app.services.parser import evaluate_result, normalize_follicles

router = APIRouter()


CORRECTION_SYSTEM_PROMPT = (
    "你是辅助生殖 B 超语音文本纠错助手。请只输出纠错后的完整文本，"
    "保持原始口述顺序，不做总结，不输出 JSON，不补写录音中没有的信息。"
)


def _normalize_endometrium_type(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text in {"A", "B", "C"}:
        return f"{text}型"
    return text


def _ground_truth_dict(gt: BUltraResult | None) -> dict[str, Any]:
    if not gt:
        return {}
    return {
        "right_follicles": normalize_follicles(gt.right_follicles or []),
        "left_follicles": normalize_follicles(gt.left_follicles or []),
        "right_follicle_total": gt.right_follicle_total or 0,
        "left_follicle_total": gt.left_follicle_total or 0,
        "endometrium_thickness": gt.endometrium_thickness,
        "endometrium_type": _normalize_endometrium_type(gt.endometrium_type),
        "right_ovary_length": gt.right_ovary_length,
        "right_ovary_width": gt.right_ovary_width,
        "left_ovary_length": gt.left_ovary_length,
        "left_ovary_width": gt.left_ovary_width,
        "remark": gt.remark,
    }


def _split_size(value: Any) -> tuple[float | None, float | None]:
    if value is None:
        return None, None
    text = str(value).strip().replace("x", "×").replace("X", "×").replace("*", "×")
    if "×" not in text:
        return None, None
    left, _, right = text.partition("×")
    try:
        return float(left), float(right)
    except (TypeError, ValueError):
        return None, None


def _follicles_from_rule_value(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return normalize_follicles(value)
    normalized_items: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            normalized_items.append(item)
        else:
            normalized_items.append({"size": item, "count": 1})
    return normalize_follicles(normalized_items)


def _normalize_rule_structured_result(fields: dict[str, Any]) -> dict[str, Any]:
    """Normalize rule parser output to the same shape used by comparisons/UI."""
    structured = dict(fields or {})

    for side in ("right", "left"):
        follicles_key = f"{side}_follicles"
        total_key = f"{side}_follicle_total"
        ovary_size_key = f"{side}_ovary_size"
        ovary_length_key = f"{side}_ovary_length"
        ovary_width_key = f"{side}_ovary_width"

        follicles = _follicles_from_rule_value(structured.get(follicles_key))
        structured[follicles_key] = follicles
        structured[total_key] = sum(int(item.get("count") or 0) for item in follicles)

        length, width = _split_size(structured.get(ovary_size_key))
        if length is not None:
            structured[ovary_length_key] = length
        if width is not None:
            structured[ovary_width_key] = width

    return structured


def _normalize_source_spans(spans: list[dict[str, Any]] | None, text: str) -> list[dict[str, Any]]:
    """Keep rule extraction source spans safe for frontend highlighting."""
    if not spans:
        return []
    text_len = len(text or "")
    normalized: list[dict[str, Any]] = []
    for span in spans:
        try:
            start = int(span.get("start", -1))
            end = int(span.get("end", -1))
        except (TypeError, ValueError):
            continue
        if start < 0 or end <= start or start >= text_len:
            continue
        end = min(end, text_len)
        field_code = str(span.get("field_code") or "").strip()
        raw_text = str(span.get("raw_text") or text[start:end])
        if raw_text and text[start:end] != raw_text:
            # Some conversion rules return offsets against an intermediate
            # normalized string. Align back to the persisted corrected_text so
            # frontend highlighting marks the exact extracted value, e.g. 18.9
            # instead of a shifted slice like 8.9。
            window_start = max(0, start - 8)
            window_end = min(text_len, end + 8)
            local_pos = text.find(raw_text, window_start, window_end)
            if local_pos < 0:
                local_pos = text.find(raw_text)
            if local_pos >= 0:
                start = local_pos
                end = local_pos + len(raw_text)
        normalized.append({
            "field_code": field_code,
            "raw_text": raw_text,
            "start": start,
            "end": end,
            "confidence": span.get("confidence"),
        })
    return normalized


async def _run_correction_llm(
    llm_model: ModelConfig,
    prompt_template: TextCorrectionTemplate | PromptTemplate,
    transcript: str,
) -> tuple[str, str]:
    llm = create_llm(
        llm_model.provider,
        endpoint=llm_model.endpoint,
        api_key=llm_model.api_key or "",
        model_name=llm_model.model_name or "",
        params=llm_model.params or {},
    )
    user_prompt = prompt_template.content.replace("{transcript}", transcript)
    if "{transcript}" not in prompt_template.content:
        user_prompt = f"{prompt_template.content}\n\n## 原始ASR\n{transcript}"

    if hasattr(llm, "_chat_complete"):
        raw = await llm._chat_complete(CORRECTION_SYSTEM_PROMPT, user_prompt, temperature=0.1)  # noqa: SLF001
        return raw.strip(), raw

    response = await llm.extract(transcript, prompt_template.content)
    return response.raw_text.strip(), response.raw_text


DEFAULT_CORRECTION_TEMPLATE = """请对以下辅助生殖 B 超 ASR 转写文本进行完整纠错，并尽量整理成便于规则提取的统一文本。

输出要求：
1. 只输出纠错后的完整文本，不输出 JSON、Markdown、解释、标题。
2. 用全角竖线“｜”分隔主要业务片段，推荐顺序：
   内膜9.5，C型｜右卵巢大小60×35，20.1，19.3，18.1｜左卵巢大小37×30，18.2，16.1｜备注无回声
3. 数字结构必须统一：
   - 中文数字、小数口述必须转为阿拉伯数字，例如“九点五”→“9.5”，“十五点零”→“15.0”。
   - 卵巢大小必须写成“长×宽”，例如“右卵巢大小六零乘三五”→“右卵巢大小60×35”。
   - 卵泡大小用逗号分隔，例如“20.1，19.3，18.1”；不要写成自然语言列表。
4. 医学名词统一为：内膜、右卵巢大小、左卵巢大小、备注。
5. 不要根据经验补写录音中没有的信息；听不清或无法确认的内容保留原文。
6. 保留必要口述顺序，但优先保证上述业务片段可被规则识别。

ASR 文本：
{transcript}
"""


async def _ensure_default_correction_template(db: AsyncSession) -> None:
    result = await db.execute(
        select(TextCorrectionTemplate).where(TextCorrectionTemplate.name == "默认完整纠错模板")
    )
    default_template = result.scalar_one_or_none()
    if default_template:
        if default_template.content != DEFAULT_CORRECTION_TEMPLATE:
            default_template.content = DEFAULT_CORRECTION_TEMPLATE
            default_template.is_default = 1
            default_template.status = "active"
        await db.commit()
        return

    db.add(
        TextCorrectionTemplate(
            name="默认完整纠错模板",
            content=DEFAULT_CORRECTION_TEMPLATE,
            is_default=1,
            status="active",
        )
    )
    await db.commit()


@router.get("/correction-templates", response_model=list[TextCorrectionTemplateOut])
async def list_correction_templates(db: AsyncSession = Depends(get_db)):
    await _ensure_default_correction_template(db)
    result = await db.execute(
        select(TextCorrectionTemplate)
        .order_by(TextCorrectionTemplate.is_default.desc(), TextCorrectionTemplate.updated_at.desc(), TextCorrectionTemplate.id.desc())
    )
    return result.scalars().all()


@router.post("/correction-templates", response_model=TextCorrectionTemplateOut)
async def create_correction_template(data: TextCorrectionTemplateCreate, db: AsyncSession = Depends(get_db)):
    name = data.name.strip()
    content = data.content.strip()
    if not name:
        raise HTTPException(status_code=400, detail="模板名称不能为空")
    if "{transcript}" not in content:
        raise HTTPException(status_code=400, detail="纠错模板必须包含 {transcript} 占位符")
    existing = (
        await db.execute(select(TextCorrectionTemplate).where(TextCorrectionTemplate.name == name))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="模板名称已存在")
    if data.is_default:
        result = await db.execute(select(TextCorrectionTemplate))
        for item in result.scalars().all():
            item.is_default = 0
    template = TextCorrectionTemplate(
        name=name,
        content=content,
        is_default=1 if data.is_default else 0,
        status="active",
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.put("/correction-templates/{template_id}", response_model=TextCorrectionTemplateOut)
async def update_correction_template(
    template_id: int,
    data: TextCorrectionTemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    template = await db.get(TextCorrectionTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="纠错模板不存在")
    update_data = data.model_dump(exclude_unset=True)
    if "name" in update_data:
        name = (update_data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="模板名称不能为空")
        existing = (
            await db.execute(
                select(TextCorrectionTemplate).where(
                    TextCorrectionTemplate.name == name,
                    TextCorrectionTemplate.id != template_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="模板名称已存在")
        template.name = name
    if "content" in update_data:
        content = (update_data["content"] or "").strip()
        if "{transcript}" not in content:
            raise HTTPException(status_code=400, detail="纠错模板必须包含 {transcript} 占位符")
        template.content = content
    if "status" in update_data and update_data["status"]:
        template.status = update_data["status"]
    if "is_default" in update_data:
        if update_data["is_default"]:
            result = await db.execute(select(TextCorrectionTemplate).where(TextCorrectionTemplate.id != template_id))
            for item in result.scalars().all():
                item.is_default = 0
        template.is_default = 1 if update_data["is_default"] else 0
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/correction-templates/{template_id}")
async def delete_correction_template(template_id: int, db: AsyncSession = Depends(get_db)):
    template = await db.get(TextCorrectionTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="纠错模板不存在")
    await db.delete(template)
    await db.commit()
    return {"message": "删除成功"}


@router.get("/runs", response_model=list[TextValidationRunOut])
async def list_validation_runs(
    exam_record_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = select(TextValidationRun).order_by(TextValidationRun.created_at.desc(), TextValidationRun.id.desc())
    if exam_record_id:
        query = query.where(TextValidationRun.exam_record_id == exam_record_id)
    result = await db.execute(query.limit(limit))
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=TextValidationRunOut)
async def get_validation_run(run_id: int, db: AsyncSession = Depends(get_db)):
    run = await db.get(TextValidationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="验证记录不存在")
    return run


@router.post("/runs", response_model=TextValidationRunOut)
async def create_validation_run(
    data: TextValidationRunCreate,
    db: AsyncSession = Depends(get_db),
):
    exam = await db.get(PatientRecord, data.exam_record_id)
    if not exam:
        raise HTTPException(status_code=404, detail="检查记录不存在")

    asr = await db.get(PatientAsrResult, data.asr_result_id)
    if not asr or asr.patient_id != exam.id:
        raise HTTPException(status_code=400, detail="ASR 结果与检查记录不匹配")
    if asr.status != "success" or not (asr.full_transcript or "").strip():
        raise HTTPException(status_code=400, detail="ASR 结果不可用于验证")

    llm_model = await db.get(ModelConfig, data.llm_model_id) if data.llm_model_id else None
    correction_template = (
        await db.get(TextCorrectionTemplate, data.correction_template_id)
        if data.correction_template_id else None
    )
    prompt = correction_template
    if not prompt and data.prompt_template_id:
        prompt = await db.get(PromptTemplate, data.prompt_template_id)
    rule_version = await db.get(ConversionConfigVersion, data.rule_version_id) if data.rule_version_id else None

    raw_asr_text = asr.full_transcript or ""
    llm_raw_output: str | None = None
    try:
        if data.corrected_text_override is not None:
            corrected_text = data.corrected_text_override.strip()
        else:
            if not llm_model or llm_model.model_type != "llm":
                raise HTTPException(status_code=400, detail="请选择 LLM 模型")
            if not prompt:
                raise HTTPException(status_code=400, detail="请选择纠错提示词")
            corrected_text, llm_raw_output = await _run_correction_llm(llm_model, prompt, raw_asr_text)

        extra_rules = await load_enabled_lexicon_rules(db, rule_version.id) if rule_version else []
        runtime_rules = await load_enabled_runtime_rules(db, rule_version.id) if rule_version else []
        conversion = run_conversion(
            corrected_text,
            conversion_version=rule_version.version_code if rule_version else data.rule_version,
            extra_confusion_rules=extra_rules,
            runtime_rules=runtime_rules,
            lexicon_mode="replace" if rule_version else "builtin",
        )
        structured = _normalize_rule_structured_result(conversion.fields or {})
        source_spans = _normalize_source_spans(conversion.source_spans or [], corrected_text)

        gt = (
            await db.execute(select(BUltraResult).where(BUltraResult.patient_id == exam.id))
        ).scalar_one_or_none()
        evaluation = evaluate_result(structured, _ground_truth_dict(gt), include_remark=False) if gt else {}

        run = TextValidationRun(
            exam_record_id=exam.id,
            asr_result_id=asr.id,
            llm_model_id=llm_model.id if llm_model else None,
            prompt_template_id=data.prompt_template_id if data.prompt_template_id else None,
            correction_template_id=correction_template.id if correction_template else None,
            rule_version_id=rule_version.id if rule_version else None,
            record_id_snapshot=exam.record_id,
            date_snapshot=asr.date,
            asr_model_name=asr.asr_model_name,
            asr_config_hash=asr.config_hash,
            llm_model_name=llm_model.name if llm_model else None,
            prompt_template_name=prompt.name if prompt else None,
            rule_version=rule_version.version_code if rule_version else data.rule_version,
            raw_asr_text=raw_asr_text,
            corrected_text=corrected_text,
            llm_raw_output=llm_raw_output,
            structured_result=structured,
            source_spans=source_spans,
            conversions=conversion.conversions,
            segments=locate_business_segments(conversion.normalized_text),
            warnings=conversion.warnings,
            risk_items=conversion.risk_result.risk_items if conversion.risk_result else [],
            evaluation=evaluation,
            accuracy=evaluation.get("accuracy") if isinstance(evaluation, dict) else None,
            status="success",
        )
    except HTTPException:
        raise
    except Exception as exc:
        run = TextValidationRun(
            exam_record_id=exam.id,
            asr_result_id=asr.id,
            llm_model_id=llm_model.id if llm_model else None,
            prompt_template_id=data.prompt_template_id if data.prompt_template_id else None,
            correction_template_id=correction_template.id if correction_template else None,
            rule_version_id=rule_version.id if rule_version else None,
            record_id_snapshot=exam.record_id,
            date_snapshot=asr.date,
            asr_model_name=asr.asr_model_name,
            asr_config_hash=asr.config_hash,
            llm_model_name=llm_model.name if llm_model else None,
            prompt_template_name=prompt.name if prompt else None,
            rule_version=rule_version.version_code if rule_version else data.rule_version,
            raw_asr_text=raw_asr_text,
            corrected_text=data.corrected_text_override or "",
            status="failed",
            error_message=str(exc),
        )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run
