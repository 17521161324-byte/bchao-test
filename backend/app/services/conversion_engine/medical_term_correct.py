"""医学术语纠错模块。

对应规则文档 02_ASR混淆词库 (C001-C032)：
- 根据 ASR 错误表达匹配标准候选
- 支持上下文约束（必要上下文、排除上下文）
- 按风险等级执行不同动作（AUTO/CANDIDATE/REVIEW/BLOCK）
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.conversion_pipeline.decision_registry import DecisionRegistry
from app.services.conversion_pipeline.types import RuleDecision


@dataclass
class MedicalTermResult:
    text: str
    conversions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ConfusionRule:
    """混淆词规则"""
    rule_id: str
    asr_error: str  # ASR 错误表达
    standard: str   # 标准候选
    scene: str      # 适用场景
    required_context: str = ""  # 必要上下文
    excluded_context: str = ""  # 排除上下文
    match_type: str = "exact"  # exact / phonetic / phrase
    risk_level: str = "medium"  # low / medium / high / highest
    action: str = "AUTO"  # AUTO / CANDIDATE / REVIEW / BLOCK
    confidence: float = 0.95
    enabled: bool = True
    notes: str = ""
    priority: int = 100  # 数值越小越先评估


# ========== 混淆词库 (C001-C032) ==========

CONFUSION_RULES: list[ConfusionRule] = [
    # --- 解剖部位 ---
    ConfusionRule("C001", "肉卵巢", "右卵巢", "卵泡监测B超",
                  required_context="大小/尺寸/数值/左卵巢/换边",
                  excluded_context="肉类",
                  match_type="phonetic", risk_level="high", action="AUTO",
                  notes="本批稳定出现，场景约束后可自动替换"),
    ConfusionRule("C002", "六碗桥大桥", "卵巢大小", "卵泡监测B超",
                  required_context="内膜/卵泡/数字/左卵巢/右卵巢",
                  match_type="phrase", risk_level="high", action="CANDIDATE",
                  notes="只生成卵巢大小候选，side=UNKNOWN；左右由业务片段组合规则判断"),
    ConfusionRule("C003", "左两条大小", "左卵巢大小", "卵泡监测B超",
                  required_context="换边/上边/尺寸",
                  match_type="phonetic", risk_level="high", action="AUTO"),
    ConfusionRule("C033", "六宛桥大桥", "卵巢大小", "卵泡监测B超",
                  required_context="内膜/卵泡/数字/左卵巢/右卵巢",
                  match_type="phrase", risk_level="high", action="CANDIDATE",
                  notes="卵巢大小近似词；仅生成UNKNOWN候选，业务片段阶段做互补侧别判断"),
    ConfusionRule("C034", "图案朝大小", "卵巢大小", "卵泡监测B超",
                  required_context="内膜/卵泡/数字/左卵巢/右卵巢",
                  match_type="phrase", risk_level="high", action="CANDIDATE",
                  notes="卵巢大小近似词；不在医学词步骤固定左右"),
    ConfusionRule("C035", "满朝大赏", "卵巢大小", "卵泡监测B超",
                  required_context="内膜/卵泡/数字/左卵巢/右卵巢",
                  match_type="phrase", risk_level="high", action="CANDIDATE",
                  notes="卵巢大小近似词；结合前一测量组侧别判定另一侧"),
    ConfusionRule("C036", "输卵管大小", "卵巢大小", "卵泡监测B超",
                  required_context="右卵巢/左卵巢/卵泡/数字",
                  match_type="phrase", risk_level="highest", action="CANDIDATE",
                  notes="输卵管为真实医学词，禁止全局替换；仅在卵泡监测测量组上下文中生成候选"),
    ConfusionRule("C037", "右耳朝外", "右卵巢外", "卵泡监测B超",
                  required_context="数字/尺寸/回声/卵泡",
                  match_type="phonetic", risk_level="highest", action="REVIEW",
                  notes="解剖部位近音候选，不能仅凭单路ASR自动替换"),
    ConfusionRule("C038", "前右卵巢外", "右卵巢外", "卵泡监测B超",
                  required_context="数字/尺寸/回声/卵泡",
                  match_type="phrase", risk_level="medium", action="AUTO",
                  notes="去除稳定口误前缀，保留明确右侧卵巢外锚点"),
    ConfusionRule("C039", "尾声欠均", "回声欠均", "卵泡监测B超",
                  required_context="内膜/面膜/内毛",
                  match_type="phonetic", risk_level="medium", action="AUTO",
                  notes="内膜超声描述近音归一；归一后字段进入备注而非内膜类型"),

    # --- 超声描述 ---
    ConfusionRule("C004", "尾生欠军", "回声欠均", "卵泡监测B超",
                  required_context="内膜/回声",
                  match_type="phonetic", risk_level="medium", action="AUTO"),
    ConfusionRule("C005", "五回声", "无回声", "卵泡监测B超",
                  required_context="尺寸/卵巢",
                  match_type="phonetic", risk_level="highest", action="REVIEW",
                  notes="否定属性，高风险，不自动替换"),
    ConfusionRule("C006", "五毫升", "无回声", "卵泡监测B超",
                  required_context="尺寸/卵巢/卵泡",
                  excluded_context="容量/液体",
                  match_type="phonetic", risk_level="highest", action="REVIEW"),
    ConfusionRule("C007", "五五三", "无回声", "卵泡监测B超",
                  required_context="尺寸/卵巢",
                  match_type="phonetic", risk_level="highest", action="REVIEW"),

    # --- 麻醉相关 ---
    ConfusionRule("C008", "芝麻", "麻醉", "取卵麻醉",
                  required_context="取卵/打/全麻/局麻",
                  excluded_context="食物/饮食/酱/吃",
                  match_type="phonetic", risk_level="high", action="AUTO"),
    ConfusionRule("C009", "进来拿钱", "静脉麻醉", "取卵麻醉",
                  required_context="麻醉/全麻/不麻",
                  match_type="phrase", risk_level="high", action="CANDIDATE"),

    # --- 胚胎处理 ---
    ConfusionRule("C010", "动胚胎", "冻胚胎", "胚胎处理",
                  required_context="取卵/移植/冻卵/胚胎",
                  match_type="phonetic", risk_level="high", action="AUTO"),
    ConfusionRule("C011", "动卵", "冻卵", "胚胎处理",
                  required_context="冻胚胎/取卵/保存",
                  match_type="phonetic", risk_level="high", action="AUTO"),
    ConfusionRule("C012", "取款", "取卵", "辅助生殖操作",
                  required_context="移植/冻胚胎/周期/手术",
                  excluded_context="金融/付款/银行/钱",
                  match_type="phonetic", risk_level="high", action="AUTO"),
    ConfusionRule("C013", "冻结抬", "冻胚胎", "胚胎处理",
                  required_context="取卵/移植/保存",
                  match_type="phrase", risk_level="high", action="CANDIDATE"),

    # --- 移植决策 ---
    ConfusionRule("C014", "取消一支", "取消移植", "移植决策",
                  required_context="血糖/怀孕/移植",
                  match_type="phrase", risk_level="highest", action="REVIEW",
                  notes="决策语义，不自动改"),

    # --- 内膜描述 ---
    ConfusionRule("C015", "粘稠性稍欠佳", "连续性稍欠佳", "卵泡监测B超",
                  required_context="内膜",
                  match_type="phrase", risk_level="highest", action="REVIEW",
                  notes="两个表达均像医学词，必须复核"),
    ConfusionRule("C016", "面膜", "内膜", "卵泡监测B超",
                  required_context="点/A型/B型/C型/卵巢/回声",
                  match_type="phonetic", risk_level="medium", action="AUTO",
                  notes="卵泡监测B超语境中的稳定内膜锚点近音词"),
    ConfusionRule("C017", "内毛", "内膜", "卵泡监测B超",
                  required_context="点/A型/B型/C型/卵巢/回声",
                  match_type="phonetic", risk_level="medium", action="AUTO",
                  notes="卵泡监测B超语境中的稳定内膜锚点近音词"),

    # --- 检查操作 ---
    ConfusionRule("C018", "底操", "B超", "检查操作",
                  required_context="做/复查/抽血/检查",
                  match_type="phonetic", risk_level="medium", action="AUTO"),
    ConfusionRule("C019", "笔插", "B超", "检查操作",
                  required_context="做/交钱/检查",
                  match_type="phonetic", risk_level="medium", action="AUTO"),
    ConfusionRule("C020", "抽鼻抽", "做B超", "检查操作",
                  required_context="过来/小便/检查",
                  match_type="phrase", risk_level="medium", action="CANDIDATE"),

    # --- 流程词 ---
    ConfusionRule("C021", "放边", "换边", "卵泡监测B超",
                  required_context="卵泡/卵巢",
                  match_type="phonetic", risk_level="high", action="AUTO"),
    ConfusionRule("C022", "收血", "抽血", "检查操作",
                  required_context="早上/结果/检验科",
                  match_type="phonetic", risk_level="medium", action="AUTO"),
    ConfusionRule("C023", "收水", "抽血", "检查操作",
                  required_context="B超/结果/早上",
                  match_type="phonetic", risk_level="medium", action="CANDIDATE"),

    # --- 医嘱 ---
    ConfusionRule("C024", "抬筋", "排精", "辅助生殖医嘱",
                  required_context="今天/促排/取卵",
                  match_type="phonetic", risk_level="high", action="CANDIDATE"),
    ConfusionRule("C025", "老胖", "卵泡", "卵泡监测B超",
                  required_context="长得/多个/大小",
                  excluded_context="体重/肥胖",
                  match_type="phonetic", risk_level="medium", action="CANDIDATE"),

    # --- 内膜分型 ---
    ConfusionRule("C026", "三级", "A型", "内膜分型",
                  required_context="内膜",
                  match_type="phonetic", risk_level="highest", action="REVIEW",
                  notes="仅凭单路ASR不可自动改"),

    # --- 移植决策（续）---
    ConfusionRule("C027", "选调得不是特别好", "血糖调得不是特别好", "移植决策",
                  required_context="移植/血糖/怀孕",
                  match_type="phrase", risk_level="highest", action="REVIEW"),
    ConfusionRule("C028", "适不适合管", "适不适合怀孕", "移植决策",
                  required_context="血糖/移植/怀孕",
                  match_type="phrase", risk_level="highest", action="REVIEW"),

    # --- 数字尺寸 ---
    ConfusionRule("C029", "三六乘一点三四", "36×34", "数字尺寸",
                  required_context="卵巢大小",
                  match_type="phrase", risk_level="highest", action="REVIEW",
                  notes="数字内容高风险"),
    ConfusionRule("C030", "一亿幺六", "×16", "数字尺寸",
                  required_context="卵巢/卵泡",
                  match_type="phrase", risk_level="highest", action="REVIEW",
                  notes="只能作为候选25×16"),
    ConfusionRule("C031", "幺八零幺", "18×15", "数字尺寸",
                  required_context="卵巢/卵泡",
                  match_type="phrase", risk_level="highest", action="REVIEW",
                  notes="多个冲突片段，必须回听"),
    ConfusionRule("C032", "三零，三零", "12.0，12.0", "卵泡数值",
                  required_context="卵泡",
                  match_type="phrase", risk_level="highest", action="BLOCK",
                  notes="不可通过词库恢复真实数值"),
]


def _check_context(text: str, pos: int, error_len: int, required: str, excluded: str) -> bool:
    """检查上下文是否满足规则条件。

    上下文格式：
    - 用 "；" 或 ";" 分隔多个独立条件（任一满足即可）
    - 每个条件内部用 "/" 或 "或" 分隔备选关键词（任一匹配即可）

    Returns:
        True = 上下文满足，可以执行转化
    """
    # 获取前后文
    context_start = max(0, pos - 80)
    context_end = min(len(text), pos + error_len + 80)
    before = text[context_start:pos]
    after = text[pos + error_len:context_end]
    context_text = before + after

    # 检查排除上下文
    if excluded:
        # 按分号分隔多个排除条件
        excluded_groups = [g.strip() for g in excluded.replace("；", ";").split(";") if g.strip()]
        for group in excluded_groups:
            # 每组内用 "/" 或 "或" 分隔备选关键词（任一匹配即排除）
            alternatives = [a.strip() for a in group.replace("或", "/").split("/") if a.strip()]
            if any(alt in context_text for alt in alternatives):
                return False

    # 检查必要上下文
    if required:
        # 按分号分隔多个必要条件（任一满足即可）
        required_groups = [g.strip() for g in required.replace("；", ";").split(";") if g.strip()]
        # 每组内用 "/" 或 "或" 分隔备选关键词（任一匹配即可）
        found = False
        for group in required_groups:
            alternatives = [a.strip() for a in group.replace("或", "/").split("/") if a.strip()]
            if any(alt in context_text for alt in alternatives):
                found = True
                break
        if not found:
            return False

    return True


def _get_scene_context(text: str) -> str:
    """推断文本的业务场景"""
    scene_keywords = {
        "卵泡监测B超": ["内膜", "卵泡", "卵巢", "大小", "回声"],
        "取卵麻醉": ["取卵", "麻醉", "全麻", "局麻", "打"],
        "胚胎处理": ["胚胎", "冻卵", "冻胚胎", "移植"],
        "移植决策": ["移植", "血糖", "取消", "怀孕"],
        "检查操作": ["B超", "抽血", "复查", "检查"],
    }

    for scene, keywords in scene_keywords.items():
        if any(kw in text for kw in keywords):
            return scene

    return "通用"


def _rule_from_dict(item: dict) -> ConfusionRule:
    return ConfusionRule(
        rule_id=str(item.get("rule_id") or item.get("rule_code") or ""),
        asr_error=str(item.get("asr_error") or item.get("error_text") or ""),
        standard=str(item.get("standard") or item.get("standard_text") or ""),
        scene=str(item.get("scene") or item.get("business_scene") or "通用"),
        required_context=str(item.get("required_context") or ""),
        excluded_context=str(item.get("excluded_context") or ""),
        match_type=str(item.get("match_type") or "exact"),
        risk_level=str(item.get("risk_level") or "medium"),
        action=str(item.get("action") or "AUTO"),
        confidence=float(item.get("confidence") if item.get("confidence") is not None else 0.95),
        enabled=bool(item.get("enabled", True)),
        notes=str(item.get("notes") or ""),
        priority=int(item.get("priority", 100)),
    )


def apply_medical_term_correct(
    text: str,
    scene: str = "",
    extra_rules: list[ConfusionRule | dict] | None = None,
    rule_mode: str = "builtin",
    decision_registry: DecisionRegistry | None = None,
    rule_version: str = "V1.0",
) -> MedicalTermResult:
    """执行医学术语纠错。

    Args:
        text: 输入文本（已经过基础清洗和数字标准化）
        scene: 业务场景，为空时自动推断
        extra_rules: 额外词库规则（数据库词条等）
        rule_mode: builtin=只使用硬编码规则；replace=数据库规则完全替代硬编码；
                   append=数据库规则追加到硬编码（仅测试场景）
        decision_registry: 决策注册表，防止高风险决策被后续低风险覆盖
        rule_version: 规则版本号

    Returns:
        MedicalTermResult 包含纠错后的文本和转化记录
    """
    result = MedicalTermResult(text=text)

    if not scene:
        scene = _get_scene_context(text)

    if rule_mode == "builtin":
        runtime_rules: list[ConfusionRule] = list(CONFUSION_RULES)
    elif rule_mode == "replace":
        runtime_rules = []
    elif rule_mode == "append":
        runtime_rules = list(CONFUSION_RULES)
    else:
        raise ValueError(f"Unsupported rule_mode: {rule_mode}")

    if extra_rules:
        for item in extra_rules:
            runtime_rules.append(item if isinstance(item, ConfusionRule) else _rule_from_dict(item))

    # 排序：优先级数字小的先评估；同优先级长表达先匹配；
    # 同位置冲突时高风险动作先评估；最终由 DecisionRegistry 防止降级覆盖。
    action_weight = {
        "BLOCK": 0,
        "REVIEW": 1,
        "CANDIDATE": 2,
        "AUTO": 3,
    }
    sorted_rules = sorted(
        runtime_rules,
        key=lambda rule: (
            int(rule.priority),
            -len(rule.asr_error),
            action_weight.get(rule.action, 9),
            rule.rule_id,
        ),
    )

    applied_rules = []  # 记录已应用的规则位置，避免重复

    for rule in sorted_rules:
        if not rule.enabled:
            continue

        # 查找所有匹配位置
        for m in re.finditer(re.escape(rule.asr_error), text):
            start = m.start()
            end = m.end()

            # 检查是否与已应用规则重叠
            if any(s <= start < e or s < end <= e for s, e in applied_rules):
                continue

            # 检查场景是否匹配
            # 规则：通用场景下允许所有规则；特定场景下只允许匹配的规则或通用规则
            if scene != "通用" and rule.scene != "通用" and rule.scene not in scene:
                # 场景不匹配时跳过
                continue

            # 检查排除上下文（排除上下文匹配时完全跳过）
            context_start = max(0, start - 80)
            context_end = min(len(text), end + 80)
            context_text = text[context_start:context_end]
            if rule.excluded_context:
                excluded_groups = [g.strip() for g in rule.excluded_context.replace("；", ";").split(";") if g.strip()]
                excluded = False
                for group in excluded_groups:
                    alternatives = [a.strip() for a in group.replace("或", "/").split("/") if a.strip()]
                    if any(alt in context_text for alt in alternatives):
                        excluded = True
                        break
                if excluded:
                    continue  # 排除上下文匹配，完全跳过此规则

            # 检查必要上下文
            if rule.required_context:
                required_groups = [g.strip() for g in rule.required_context.replace("；", ";").split(";") if g.strip()]
                found = False
                for group in required_groups:
                    alternatives = [a.strip() for a in group.replace("或", "/").split("/") if a.strip()]
                    if any(alt in context_text for alt in alternatives):
                        found = True
                        break
                if not found:
                    # 必要上下文不满足时，降级为 CANDIDATE 或跳过
                    if rule.action == "AUTO":
                        action = "CANDIDATE"
                    elif rule.action in ("CANDIDATE", "REVIEW", "BLOCK"):
                        action = rule.action
                    else:
                        continue
                else:
                    action = rule.action
            else:
                action = rule.action

            # 决策注册表拦截：防止高风险决策被后续低风险覆盖
            if decision_registry is not None:
                decision = RuleDecision(
                    rule_id=rule.rule_id,
                    rule_version=rule_version,
                    step_code="MEDICAL_TERM",
                    action=action,
                    category="medical_term",
                    raw=rule.asr_error,
                    converted=rule.standard,
                    start=start,
                    end=end,
                    risk_level=rule.risk_level,
                    confidence=rule.confidence,
                )
                if not decision_registry.register(decision):
                    continue

            # 执行替换
            if action == "AUTO":
                new_text = text[:start] + rule.standard + text[end:]
                result.conversions.append({
                    "rule_id": rule.rule_id,
                    "raw": rule.asr_error,
                    "converted": rule.standard,
                    "action": "AUTO",
                    "category": "medical_term",
                    "start": start,
                    "end": end,
                    "risk_level": rule.risk_level,
                    "notes": rule.notes,
                })
                text = new_text
                # 更新后续位置偏移
                offset = len(rule.standard) - len(rule.asr_error)
                applied_rules = [(s + offset if s > start else s, e + offset if e > start else e) for s, e in applied_rules]
                applied_rules.append((start, start + len(rule.standard)))
            elif action == "CANDIDATE":
                # 候选：不修改原文，仅记录候选（前端单独显示，不再注入文本标记）
                result.conversions.append({
                    "rule_id": rule.rule_id,
                    "raw": rule.asr_error,
                    "converted": rule.standard,
                    "action": "CANDIDATE",
                    "category": "medical_term",
                    "start": start,
                    "end": end,
                    "risk_level": rule.risk_level,
                    "confidence": rule.confidence,
                    "notes": rule.notes,
                })
                applied_rules.append((start, end))
            elif action == "REVIEW":
                # 审核：标记但不修改原文
                result.conversions.append({
                    "rule_id": rule.rule_id,
                    "raw": rule.asr_error,
                    "converted": rule.standard,
                    "action": "REVIEW",
                    "category": "medical_term",
                    "start": start,
                    "end": end,
                    "risk_level": rule.risk_level,
                    "notes": rule.notes,
                })
                result.warnings.append(f"【待复核】{rule.asr_error} → {rule.standard}（{rule.notes or '高风险'}）")
                applied_rules.append((start, end))
            elif action == "BLOCK":
                # 阻断：标记并添加警告
                result.conversions.append({
                    "rule_id": rule.rule_id,
                    "raw": rule.asr_error,
                    "converted": rule.standard,
                    "action": "BLOCK",
                    "category": "medical_term",
                    "start": start,
                    "end": end,
                    "risk_level": rule.risk_level,
                    "notes": rule.notes,
                })
                result.warnings.append(f"【阻断】{rule.asr_error}：{rule.notes or '不可自动处理'}")
                applied_rules.append((start, end))

    result.text = text
    return result
