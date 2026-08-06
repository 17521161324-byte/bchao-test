"""ASR conversion configuration API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.conversion_config import (
    ConversionConfigVersion,
    ConversionLexiconEntry,
    ConversionRuleEntry,
)
from app.schemas.conversion_config import (
    BuiltinRulesOut,
    ConversionLexiconCreate,
    ConversionLexiconOut,
    ConversionLexiconUpdate,
    ConversionPreviewOut,
    ConversionPreviewRequest,
    ConversionRuleCreate,
    ConversionRuleOut,
    ConversionRuleUpdate,
    ConversionVersionClone,
    ConversionVersionCreate,
    ConversionVersionOut,
    ConversionVersionUpdate,
)
from app.services.conversion_config import (
    count_version_items,
    ensure_default_version,
    get_builtin_rules,
    load_enabled_lexicon_rules,
    load_enabled_runtime_rules,
    load_version_by_selector,
    publish_version,
)

router = APIRouter()

EDITABLE_VERSION_STATUSES = {"draft", "testing"}


async def _version_out(db: AsyncSession, version: ConversionConfigVersion) -> ConversionVersionOut:
    lexicon_count, rule_count = await count_version_items(db, version.id)
    data = ConversionVersionOut.model_validate(version)
    data.lexicon_count = lexicon_count
    data.rule_count = rule_count
    return data


async def _get_version_or_404(db: AsyncSession, version_id: int) -> ConversionConfigVersion:
    version = await db.get(ConversionConfigVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="配置版本不存在")
    return version


def _ensure_editable(version: ConversionConfigVersion):
    if version.status == "published":
        raise HTTPException(status_code=409, detail="已发布版本不可直接修改，请克隆为草稿后编辑")


def _ensure_editable_status(status: str):
    if status not in EDITABLE_VERSION_STATUSES:
        raise HTTPException(status_code=400, detail="版本状态只能通过发布/回滚接口变更")


@router.get("/builtin-rules", response_model=BuiltinRulesOut)
async def list_builtin_rules():
    """内置规则清单元数据（只读展示）：文本切换 / 数据提取 / 警示规则。

    与版本无关；警示组直接映射 risk_intercept.RISK_RULES，保证与引擎同步。
    """
    return get_builtin_rules()


@router.post("/init-defaults", response_model=ConversionVersionOut)
async def init_defaults(db: AsyncSession = Depends(get_db)):
    version = await ensure_default_version(db)
    return await _version_out(db, version)


@router.get("/versions", response_model=list[ConversionVersionOut])
async def list_versions(db: AsyncSession = Depends(get_db)):
    versions = (
        await db.execute(select(ConversionConfigVersion).order_by(ConversionConfigVersion.updated_at.desc(), ConversionConfigVersion.id.desc()))
    ).scalars().all()
    return [await _version_out(db, item) for item in versions]


@router.post("/versions", response_model=ConversionVersionOut)
async def create_version(data: ConversionVersionCreate, db: AsyncSession = Depends(get_db)):
    _ensure_editable_status(data.status)
    existing = (
        await db.execute(select(ConversionConfigVersion).where(ConversionConfigVersion.version_code == data.version_code))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="版本编码已存在")
    version = ConversionConfigVersion(**data.model_dump())
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return await _version_out(db, version)


@router.put("/versions/{version_id}", response_model=ConversionVersionOut)
async def update_version(version_id: int, data: ConversionVersionUpdate, db: AsyncSession = Depends(get_db)):
    version = await _get_version_or_404(db, version_id)
    _ensure_editable(version)
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "status" and value is not None:
            _ensure_editable_status(value)
        setattr(version, key, value)
    await db.commit()
    await db.refresh(version)
    return await _version_out(db, version)


@router.post("/versions/{version_id}/clone", response_model=ConversionVersionOut)
async def clone_version(version_id: int, data: ConversionVersionClone, db: AsyncSession = Depends(get_db)):
    source = await _get_version_or_404(db, version_id)
    existing = (
        await db.execute(select(ConversionConfigVersion).where(ConversionConfigVersion.version_code == data.version_code))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="版本编码已存在")

    cloned = ConversionConfigVersion(
        version_code=data.version_code,
        version_name=data.version_name,
        description=data.description or f"从 {source.version_code} 克隆",
        status="draft",
        parent_version_id=source.id,
    )
    db.add(cloned)
    await db.flush()

    lexicons = (
        await db.execute(select(ConversionLexiconEntry).where(ConversionLexiconEntry.version_id == source.id))
    ).scalars().all()
    for item in lexicons:
        db.add(ConversionLexiconEntry(
            version_id=cloned.id,
            rule_code=item.rule_code,
            error_text=item.error_text,
            standard_text=item.standard_text,
            asr_model=item.asr_model,
            business_scene=item.business_scene,
            required_context=item.required_context,
            excluded_context=item.excluded_context,
            match_type=item.match_type,
            action=item.action,
            risk_level=item.risk_level,
            confidence=item.confidence,
            priority=item.priority,
            enabled=item.enabled,
            notes=item.notes,
        ))

    rules = (
        await db.execute(select(ConversionRuleEntry).where(ConversionRuleEntry.version_id == source.id))
    ).scalars().all()
    for item in rules:
        db.add(ConversionRuleEntry(
            version_id=cloned.id,
            rule_code=item.rule_code,
            rule_type=item.rule_type,
            name=item.name,
            description=item.description,
            pattern=item.pattern,
            replacement=item.replacement,
            condition_config=item.condition_config or {},
            example_input=item.example_input,
            example_output=item.example_output,
            action=item.action,
            risk_level=item.risk_level,
            priority=item.priority,
            enabled=item.enabled,
            editable=item.editable,
            system_handler=item.system_handler,
            notes=item.notes,
        ))

    await db.commit()
    await db.refresh(cloned)
    return await _version_out(db, cloned)


@router.post("/versions/{version_id}/publish", response_model=ConversionVersionOut)
async def publish(version_id: int, db: AsyncSession = Depends(get_db)):
    version = await _get_version_or_404(db, version_id)
    version = await publish_version(db, version)
    return await _version_out(db, version)


@router.post("/versions/{version_id}/rollback", response_model=ConversionVersionOut)
async def rollback(version_id: int, db: AsyncSession = Depends(get_db)):
    version = await _get_version_or_404(db, version_id)
    version = await publish_version(db, version)
    return await _version_out(db, version)


@router.delete("/versions/{version_id}")
async def delete_version(version_id: int, db: AsyncSession = Depends(get_db)):
    """删除版本：仅 draft/testing（草稿/测试中）可删除，级联删除其词库与规则条目。

    已发布（published）与已回滚（rolled_back）版本不可删除——已发布是当前生效规则，
    已回滚保留历史供重新发布恢复。
    """
    version = await _get_version_or_404(db, version_id)
    if version.status not in ("draft", "testing"):
        raise HTTPException(status_code=409, detail="仅草稿/测试中版本可删除，已发布或已回滚版本不可删除")
    await db.execute(delete(ConversionLexiconEntry).where(ConversionLexiconEntry.version_id == version_id))
    await db.execute(delete(ConversionRuleEntry).where(ConversionRuleEntry.version_id == version_id))
    await db.delete(version)
    await db.commit()
    return {"message": "删除成功"}


@router.get("/versions/{version_id}/lexicon", response_model=list[ConversionLexiconOut])
async def list_lexicon(version_id: int, db: AsyncSession = Depends(get_db)):
    await _get_version_or_404(db, version_id)
    rows = (
        await db.execute(
            select(ConversionLexiconEntry)
            .where(ConversionLexiconEntry.version_id == version_id)
            .order_by(ConversionLexiconEntry.priority.asc(), ConversionLexiconEntry.id.asc())
        )
    ).scalars().all()
    return rows


@router.post("/versions/{version_id}/lexicon", response_model=ConversionLexiconOut)
async def create_lexicon(version_id: int, data: ConversionLexiconCreate, db: AsyncSession = Depends(get_db)):
    version = await _get_version_or_404(db, version_id)
    _ensure_editable(version)
    row = ConversionLexiconEntry(version_id=version_id, **data.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/lexicon/{entry_id}", response_model=ConversionLexiconOut)
async def update_lexicon(entry_id: int, data: ConversionLexiconUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(ConversionLexiconEntry, entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="词库条目不存在")
    version = await _get_version_or_404(db, row.version_id)
    _ensure_editable(version)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/lexicon/{entry_id}")
async def delete_lexicon(entry_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(ConversionLexiconEntry, entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="词库条目不存在")
    version = await _get_version_or_404(db, row.version_id)
    _ensure_editable(version)
    await db.delete(row)
    await db.commit()
    return {"message": "删除成功"}


@router.get("/versions/{version_id}/rules", response_model=list[ConversionRuleOut])
async def list_rules(version_id: int, db: AsyncSession = Depends(get_db)):
    await _get_version_or_404(db, version_id)
    rows = (
        await db.execute(
            select(ConversionRuleEntry)
            .where(ConversionRuleEntry.version_id == version_id)
            .order_by(ConversionRuleEntry.priority.asc(), ConversionRuleEntry.id.asc())
        )
    ).scalars().all()
    return rows


@router.post("/versions/{version_id}/rules", response_model=ConversionRuleOut)
async def create_rule(version_id: int, data: ConversionRuleCreate, db: AsyncSession = Depends(get_db)):
    version = await _get_version_or_404(db, version_id)
    _ensure_editable(version)
    row = ConversionRuleEntry(version_id=version_id, **data.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/rules/{entry_id}", response_model=ConversionRuleOut)
async def update_rule(entry_id: int, data: ConversionRuleUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(ConversionRuleEntry, entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    version = await _get_version_or_404(db, row.version_id)
    _ensure_editable(version)
    if not row.editable:
        raise HTTPException(status_code=409, detail="系统规则不可直接编辑")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/rules/{entry_id}")
async def delete_rule(entry_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(ConversionRuleEntry, entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    version = await _get_version_or_404(db, row.version_id)
    _ensure_editable(version)
    if not row.editable:
        raise HTTPException(status_code=409, detail="系统规则不可删除")
    await db.delete(row)
    await db.commit()
    return {"message": "删除成功"}


@router.post("/preview", response_model=ConversionPreviewOut)
async def preview(data: ConversionPreviewRequest, db: AsyncSession = Depends(get_db)):
    from app.services.conversion_engine import run_conversion
    from app.services.conversion_engine.business_segment_locator import locate_business_segments

    version = await load_version_by_selector(db, version_id=data.version_id, version_code=data.version_code)
    extra_rules = await load_enabled_lexicon_rules(db, version.id) if version else []
    runtime_rules = await load_enabled_runtime_rules(db, version.id) if version else []
    result = run_conversion(
        raw_text=data.text,
        scene=data.scene,
        model_name=data.model_name,
        conversion_version=version.version_code if version else "manual",
        skip_conversion=data.skip_conversion,
        extra_confusion_rules=extra_rules,
        runtime_rules=runtime_rules,
        lexicon_mode="replace" if version else "builtin",
    )
    return ConversionPreviewOut(
        raw_text=result.raw_text,
        converted_text=result.normalized_text,
        conversions=result.conversions,
        warnings=result.warnings,
        fields=result.fields,
        source_spans=result.source_spans,
        segments=locate_business_segments(result.normalized_text),
        risk_items=result.risk_result.risk_items if result.risk_result else [],
        risk_passed=result.risk_passed,
        risk_blocked=result.risk_blocked,
        version=await _version_out(db, version) if version else None,
        steps=[step.__dict__ if hasattr(step, "__dict__") else step for step in (result.steps or [])],
        result_level=(result.result_level.value if hasattr(result.result_level, "value") else str(result.result_level or "AUTO_ACCEPT")),
        config_hash=result.config_hash or "",
    )
