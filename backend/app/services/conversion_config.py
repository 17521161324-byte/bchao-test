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


async def build_version_config_hash(db: AsyncSession, version: ConversionConfigVersion) -> str:
    """计算版本当前配置快照哈希（P0-10 发布门槛）。

    与流水线执行创建时 _build_snapshot 对同一版本的哈希口径保持一致：
    version 元信息 + 启用的词库规则 + 启用的参数化规则 + lexicon_mode。
    """
    from app.services.conversion_pipeline.orchestrator import build_config_hash

    lexicon_rules = await load_enabled_lexicon_rules(db, version.id)
    runtime_rules = await load_enabled_runtime_rules(db, version.id)
    snapshot = {
        "version": {
            "id": version.id,
            "version_code": version.version_code,
            "status": version.status,
        },
        "lexicon_rules": lexicon_rules,
        "runtime_rules": runtime_rules,
        "lexicon_mode": "append",
    }
    return build_config_hash(snapshot)


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
    {"rule_code": "F002", "name": "内膜类型", "description": "仅接受内膜业务窗口内的 A/B/C 型；回声欠均等描述进入备注。", "field_code": "endometrium_type", "range": "A/B/C 型"},
    {"rule_code": "F003", "name": "右卵巢大小", "description": "右卵巢长×宽，每维范围 10-100mm。", "field_code": "right_ovary_size", "range": "10-100mm/维"},
    {"rule_code": "F004", "name": "左卵巢大小", "description": "左卵巢长×宽，每维范围 10-100mm。", "field_code": "left_ovary_size", "range": "10-100mm/维"},
    {"rule_code": "F005", "name": "右侧当前状态", "description": "检测到右/换边词后当前侧别置为右侧。", "field_code": "current_side", "range": "RIGHT"},
    {"rule_code": "F006", "name": "左侧当前状态", "description": "检测到左/换边词后当前侧别置为左侧。", "field_code": "current_side", "range": "LEFT"},
    {"rule_code": "F007", "name": "右卵泡列表", "description": "右卵巢大小之后的小数序列，常规 2-40mm，>40mm 保留并警示。", "field_code": "right_follicles", "range": "2-40mm 常规，>40mm 警示"},
    {"rule_code": "F008", "name": "左卵泡列表", "description": "左卵巢大小之后的小数序列，常规 2-40mm，>40mm 保留并警示。", "field_code": "left_follicles", "range": "2-40mm 常规，>40mm 警示"},
    {"rule_code": "F009", "name": "超声描述归备注", "description": "无回声/强回声/回声欠均/宫腔分离等医学描述写入备注，不冒充内膜类型。", "field_code": "remark", "range": "-"},
    {"rule_code": "F010", "name": "操作信息", "description": "取卵/移植/冻胚胎/麻醉等操作，支持取消/否定修饰。", "field_code": "procedure_info", "range": "-"},
    {"rule_code": "F011", "name": "随访医嘱", "description": "抽血/空腹/复诊等医嘱关键词。", "field_code": "followup_orders", "range": "-"},
    {"rule_code": "F012", "name": "提及数量", "description": "口述卵泡数量（如三个）。", "field_code": "mentioned_count", "range": "-"},
    {"rule_code": "F013", "name": "噪声片段", "description": "口语/噪声词，不参与抽取。", "field_code": "noise_segment", "range": "-"},
    {"rule_code": "F014", "name": "来源追踪", "description": "每个解析字段的原文位置（source span），供前端高亮。", "field_code": "source_span", "range": "-"},
]


def get_builtin_rules() -> dict[str, list[dict]]:
    """返回真实 CORE 规则清单，供执行诊断判断“已配置/已调用/命中”。"""
    from app.services.conversion_engine.risk_intercept import RISK_RULES

    medical_term = [
        {
            "rule_code": rule.rule_id,
            "name": f"{rule.asr_error} → {rule.standard}",
            "description": rule.notes or f"{rule.match_type} 医学词规则",
            "action": rule.action,
            "system_handler": "apply_medical_term_correct",
        }
        for rule in CONFUSION_RULES
        if rule.enabled
    ]
    medical_term.extend([
        {"rule_code": "M003", "name": "标准内膜类型识别", "description": "内膜窗口内明确 A/B/C型、形、性，归一为A/B/C型。", "action": "AUTO", "system_handler": "collect_endometrium_type_rule_items"},
        {"rule_code": "M005", "name": "内膜类型识别窗口", "description": "只在内膜锚点之后、下一核心卵巢锚点/强边界之前识别类型。", "action": "AUTO", "system_handler": "collect_endometrium_type_rule_items"},
        {"rule_code": "M006", "name": "多内膜类型冲突", "description": "同一内膜窗口出现多个完整类型时仅生成最后完整类型候选并进入REVIEW。", "action": "REVIEW", "system_handler": "collect_endometrium_type_rule_items"},
        {"rule_code": "M007", "name": "疑似内膜类型近音词", "description": "飞行/地形/黑皮等只标记疑似类型，禁止盲猜A/B/C。", "action": "REVIEW", "system_handler": "collect_endometrium_type_rule_items"},
    ])

    number_rules = [
        {"rule_code": code, "name": name, "description": desc, "action": action, "system_handler": handler}
        for code, name, desc, action, handler in [
            ("D001", "乘一误识尺寸候选", "乘一误识为乘以的尺寸处理。", "AUTO", "parse_dimension_candidates"),
            ("D002", "异常小数尺寸重建", "异常小数尺寸仅生成REVIEW候选。", "REVIEW", "parse_dimension_candidates"),
            ("D003", "卵巢维度缺失", "缺失首维输出??×N并BLOCK。", "BLOCK", "parse_dimension_candidates"),
            ("N001", "中文小数转数字", "完整中文小数转阿拉伯数字。", "AUTO", "apply_number_normalize"),
            ("N002", "幺数字归一", "明确数值语境中的幺按1处理。", "AUTO", "apply_number_normalize"),
            ("N003", "乘法连接词统一", "明确二维尺寸中的乘/乘以统一为×，保护医学词边界。", "AUTO", "apply_number_normalize"),
            ("N004", "单位统一", "毫米/厘米/毫升等单位格式统一。", "AUTO", "apply_number_normalize"),
            ("N005", "A/B/C格式化", "明确A/B/C类型格式归一。", "AUTO", "apply_number_normalize"),
            ("N006", "中文四位尺寸候选", "连续四位中文数字只生成尺寸候选，不覆盖原文。", "CANDIDATE", "apply_number_normalize"),
            ("N007", "数字四位尺寸候选", "连续四位数字只生成尺寸候选，不覆盖原文。", "CANDIDATE", "apply_number_normalize"),
            ("N009", "异常小数尺寸候选", "异常小数尺寸进入REVIEW，不覆盖原文。", "REVIEW", "apply_number_normalize"),
            ("N010", "连续小数切分候选", "连续小数序列仅生成候选元数据。", "CANDIDATE", "apply_number_normalize"),
            ("N011", "重复数量候选", "数字+两个/三个等只生成重复候选。", "CANDIDATE", "apply_number_normalize"),
            ("N012", "数值列表标点恢复", "业务数值列表中的空格分隔转中文逗号。", "AUTO", "apply_number_normalize"),
        ]
    ]

    business_segment = [
        {"rule_code": "S006", "name": "后置明确侧别反推模糊卵巢大小", "description": "模糊大小候选在后文明示另一侧前时按互补侧别生成REVIEW候选。", "action": "REVIEW", "system_handler": "collect_fuzzy_ovary_inferences"},
        {"rule_code": "S010", "name": "后置明确侧别反推前置匿名卵巢段", "description": "匿名二维尺寸+连续卵泡组在后文首次明确一侧时归为另一侧候选。", "action": "REVIEW", "system_handler": "collect_anonymous_ovary_groups"},
        {"rule_code": "S011", "name": "重复卵巢测量组互补侧别", "description": "前一测量组侧别已知，后续模糊大小候选形成新测量组时推断另一侧。", "action": "REVIEW", "system_handler": "collect_fuzzy_ovary_inferences"},
        {"rule_code": "S012", "name": "数值+A/B/C型反推内膜段", "description": "不在左右卵巢段内的明确小数+A/B/C型建立内膜段。", "action": "AUTO", "system_handler": "collect_inferred_endometrium_pairs"},
        *TEXT_SWITCH_RULES,
    ]

    return {
        "medical_term": medical_term,
        "number_normalize": number_rules,
        "business_segment": business_segment,
        "text_switch": [],
        "field_extract": FIELD_EXTRACT_RULES,
        "base_cleaning": [
            {"rule_code": "B001", "name": "移除ASR伪标签", "description": "移除 language chinese <asr_text> 等伪标签。", "action": "AUTO", "system_handler": "apply_base_cleaning"},
            {"rule_code": "B002", "name": "提取ASR文本内容", "description": "提取 <asr_text> 闭合标签内的内容。", "action": "AUTO", "system_handler": "apply_base_cleaning"},
            {"rule_code": "B003", "name": "过滤language前缀", "description": "过滤开头的 language chinese 前缀。", "action": "AUTO", "system_handler": "apply_base_cleaning"},
            {"rule_code": "B004", "name": "清除异常空格", "description": "移除中英文间及连续多余空格。", "action": "AUTO", "system_handler": "apply_base_cleaning"},
            {"rule_code": "B005", "name": "恢复数值列表标点", "description": "在业务数值列表间恢复中文逗号。", "action": "AUTO", "system_handler": "apply_base_cleaning"},
        ],
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
