"""Helpers for ASR conversion configuration versions."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversion_config import (
    ConversionConfigVersion,
    ConversionLexiconEntry,
    ConversionRuleEntry,
)
from app.services.conversion_engine.medical_term_correct import CONFUSION_RULES


SYSTEM_RULES = [
    {
        "rule_code": "B001",
        "rule_type": "base_cleaning",
        "name": "基础文本清洗",
        "description": "清理空白、重复标点、明显口语停顿和无效片段。",
        "system_handler": "apply_base_cleaning",
        "editable": 0,
        "priority": 10,
    },
    {
        "rule_code": "N001",
        "rule_type": "number_normalize",
        "name": "中文数字标准化",
        "description": "把九点二、三九乘三零等表达标准化为结构化数字文本。",
        "system_handler": "apply_number_normalize",
        "editable": 0,
        "priority": 20,
    },
    {
        "rule_code": "M001",
        "rule_type": "medical_term",
        "name": "医学混淆词纠正",
        "description": "根据词库、上下文和风险等级处理 ASR 混淆词。",
        "system_handler": "apply_medical_term_correct",
        "editable": 0,
        "priority": 30,
    },
    {
        "rule_code": "F001",
        "rule_type": "field_parse",
        "name": "字段预解析",
        "description": "从转化后文本中预解析内膜、卵巢、卵泡等字段。",
        "system_handler": "parse_fields",
        "editable": 0,
        "priority": 40,
    },
    {
        "rule_code": "R001",
        "rule_type": "risk_intercept",
        "name": "风险拦截",
        "description": "拦截左右侧、否定语义、关键数字变化等高风险转化。",
        "system_handler": "check_risks",
        "editable": 0,
        "priority": 50,
    },
]


async def count_version_items(db: AsyncSession, version_id: int) -> tuple[int, int]:
    lexicon_count = await db.scalar(
        select(func.count()).select_from(ConversionLexiconEntry).where(ConversionLexiconEntry.version_id == version_id)
    )
    rule_count = await db.scalar(
        select(func.count()).select_from(ConversionRuleEntry).where(ConversionRuleEntry.version_id == version_id)
    )
    return int(lexicon_count or 0), int(rule_count or 0)


async def ensure_default_version(db: AsyncSession) -> ConversionConfigVersion:
    existing = (
        await db.execute(select(ConversionConfigVersion).where(ConversionConfigVersion.version_code == "V1.0"))
    ).scalar_one_or_none()
    if existing:
        return existing

    version = ConversionConfigVersion(
        version_code="V1.0",
        version_name="默认转化规则 V1.0",
        status="published",
        description="从当前硬编码混淆词库和系统转化链路导入的默认版本。",
        published_at=datetime.utcnow(),
    )
    db.add(version)
    await db.flush()

    for rule in CONFUSION_RULES:
        db.add(ConversionLexiconEntry(
            version_id=version.id,
            rule_code=rule.rule_id,
            error_text=rule.asr_error,
            standard_text=rule.standard,
            business_scene=rule.scene,
            required_context=rule.required_context,
            excluded_context=rule.excluded_context,
            match_type=rule.match_type,
            action=rule.action,
            risk_level=rule.risk_level,
            confidence=rule.confidence,
            enabled=1 if rule.enabled else 0,
            notes=rule.notes,
        ))

    for item in SYSTEM_RULES:
        db.add(ConversionRuleEntry(
            version_id=version.id,
            rule_code=item["rule_code"],
            rule_type=item["rule_type"],
            name=item["name"],
            description=item["description"],
            system_handler=item["system_handler"],
            editable=int(item["editable"]),
            priority=int(item["priority"]),
            enabled=1,
        ))

    await db.commit()
    await db.refresh(version)
    return version


async def load_version_by_selector(
    db: AsyncSession,
    *,
    version_id: int | None = None,
    version_code: str | None = None,
) -> ConversionConfigVersion | None:
    if version_id:
        return await db.get(ConversionConfigVersion, version_id)
    if version_code:
        return (
            await db.execute(select(ConversionConfigVersion).where(ConversionConfigVersion.version_code == version_code))
        ).scalar_one_or_none()
    return (
        await db.execute(select(ConversionConfigVersion).where(ConversionConfigVersion.status == "published"))
    ).scalars().first()


async def load_enabled_lexicon_rules(db: AsyncSession, version_id: int) -> list[dict]:
    rows = (
        await db.execute(
            select(ConversionLexiconEntry)
            .where(ConversionLexiconEntry.version_id == version_id, ConversionLexiconEntry.enabled == 1)
            .order_by(ConversionLexiconEntry.priority.asc(), ConversionLexiconEntry.id.asc())
        )
    ).scalars().all()
    return [
        {
            "rule_id": row.rule_code,
            "asr_error": row.error_text,
            "standard": row.standard_text,
            "scene": row.business_scene or "通用",
            "required_context": row.required_context or "",
            "excluded_context": row.excluded_context or "",
            "match_type": row.match_type or "exact",
            "risk_level": row.risk_level or "medium",
            "action": row.action or "AUTO",
            "confidence": float(row.confidence if row.confidence is not None else 0.95),
            "enabled": bool(row.enabled),
            "notes": row.notes or "",
            "priority": int(row.priority or 100),
        }
        for row in rows
    ]


async def load_enabled_runtime_rules(
    db: AsyncSession,
    version_id: int,
) -> list[dict]:
    """加载启用中的参数化规则（editable=1），供流水线参数化规则步骤执行。

    对应改造计划 Task 10。handler 白名单校验在 runtime_rule_executor 执行时进行。
    """
    rows = (
        await db.execute(
            select(ConversionRuleEntry)
            .where(
                ConversionRuleEntry.version_id == version_id,
                ConversionRuleEntry.enabled == 1,
                ConversionRuleEntry.editable == 1,
            )
            .order_by(
                ConversionRuleEntry.priority.asc(),
                ConversionRuleEntry.id.asc(),
            )
        )
    ).scalars().all()

    return [
        {
            "rule_code": row.rule_code,
            "rule_type": row.rule_type,
            "name": row.name,
            "description": row.description,
            "pattern": row.pattern,
            "replacement": row.replacement,
            "condition_config": row.condition_config or {},
            "action": row.action,
            "risk_level": row.risk_level,
            "priority": row.priority,
            "enabled": bool(row.enabled),
            "system_handler": row.system_handler,
        }
        for row in rows
    ]


async def publish_version(db: AsyncSession, version: ConversionConfigVersion) -> ConversionConfigVersion:
    await db.execute(
        update(ConversionConfigVersion)
        .where(ConversionConfigVersion.status == "published", ConversionConfigVersion.id != version.id)
        .values(status="rolled_back", updated_at=datetime.utcnow())
    )
    version.status = "published"
    version.published_at = datetime.utcnow()
    await db.commit()
    await db.refresh(version)
    return version


# ========== 内置规则清单元数据（只读展示用） ==========
# 与引擎实现一一对应：文本切换 → business_segment_locator.py，
# 数据提取 → field_parser.py（F001-F014），警示 → risk_intercept.py（R001-R017）。
# 警示组直接序列化 RISK_RULES，避免清单与引擎行为不一致。

TEXT_SWITCH_RULES = [
    {
        "rule_code": "SW001",
        "name": "左右定位词",
        "description": "右卵巢/左卵巢/右边/左边/右侧/左侧等显式定位词，确定后续数据的侧别归属。",
        "system_handler": "locate_business_segments",
    },
    {
        "rule_code": "SW002",
        "name": "换边词切换",
        "description": "换边/放边/另一边/到左边/到右边等换边词，出现时切换当前侧别。",
        "system_handler": "locate_business_segments",
    },
    {
        "rule_code": "SW003",
        "name": "缺失定位词侧别继承",
        "description": "缺少单个定位词时按最近明确侧别继承（240 字符窗口）；句号/感叹号/问号/换行等强边界停止继承。",
        "system_handler": "locate_business_segments",
    },
]

FIELD_EXTRACT_RULES = [
    {"rule_code": "F001", "name": "内膜厚度", "description": "内膜定位词后首个小数，范围 1-30mm。", "field_code": "endometrium_thickness", "range": "1-30mm"},
    {"rule_code": "F002", "name": "内膜类型", "description": "内膜分型 A/B/C 型（含回声欠均等描述）。", "field_code": "endometrium_type", "range": "A/B/C 型"},
    {"rule_code": "F003", "name": "右卵巢大小", "description": "右卵巢长×宽，每维范围 10-100mm。", "field_code": "right_ovary_size", "range": "10-100mm/维"},
    {"rule_code": "F004", "name": "左卵巢大小", "description": "左卵巢长×宽，每维范围 10-100mm。", "field_code": "left_ovary_size", "range": "10-100mm/维"},
    {"rule_code": "F005", "name": "右侧当前状态", "description": "检测到右/换边词后当前侧别置为右侧。", "field_code": "current_side", "range": "RIGHT"},
    {"rule_code": "F006", "name": "左侧当前状态", "description": "检测到左/换边词后当前侧别置为左侧。", "field_code": "current_side", "range": "LEFT"},
    {"rule_code": "F007", "name": "右卵泡列表", "description": "右卵巢大小之后的小数序列，常规 2-40mm，>40mm 保留并警示。", "field_code": "right_follicles", "range": "2-40mm 常规，>40mm 警示"},
    {"rule_code": "F008", "name": "左卵泡列表", "description": "左卵巢大小之后的小数序列，常规 2-40mm，>40mm 保留并警示。", "field_code": "left_follicles", "range": "2-40mm 常规，>40mm 警示"},
    {"rule_code": "F009", "name": "超声发现", "description": "无回声/强回声/回声欠均等超声描述，支持否定修饰。", "field_code": "ultrasound_findings", "range": "-"},
    {"rule_code": "F010", "name": "操作信息", "description": "取卵/移植/冻胚胎/麻醉等操作，支持取消/否定修饰。", "field_code": "procedure_info", "range": "-"},
    {"rule_code": "F011", "name": "随访医嘱", "description": "抽血/空腹/复诊等医嘱关键词。", "field_code": "followup_orders", "range": "-"},
    {"rule_code": "F012", "name": "提及数量", "description": "口述卵泡数量（如三个）。", "field_code": "mentioned_count", "range": "-"},
    {"rule_code": "F013", "name": "噪声片段", "description": "口语/噪声词，不参与抽取。", "field_code": "noise_segment", "range": "-"},
    {"rule_code": "F014", "name": "来源追踪", "description": "每个解析字段的原文位置（source span），供前端高亮。", "field_code": "source_span", "range": "-"},
]


def get_builtin_rules() -> dict[str, list[dict]]:
    """返回内置规则清单元数据（只读展示用）。

    三组：text_switch（文本切换 SW001-SW003）、field_extract（数据提取 F001-F014）、
    risk（警示规则 R001-R017，直接序列化 risk_intercept.RISK_RULES 保证与引擎同步）。
    """
    from app.services.conversion_engine.risk_intercept import RISK_RULES

    return {
        "text_switch": TEXT_SWITCH_RULES,
        "field_extract": FIELD_EXTRACT_RULES,
        "risk": [
            {
                "rule_code": rule.rule_id,
                "name": rule.name,
                "description": rule.description,
                "severity": rule.severity,
                "action": rule.action,
            }
            for rule in RISK_RULES
        ],
    }
