"""风险拦截模块。

对应规则文档 05_风险拦截规则 (R001-R015)：
- R001: ASR状态非成功或文本为空 → BLOCK
- R002: 同一片段连续重复≥3次 → 截断+REVIEW
- R003: 标准化后长度超过中位数3倍 → 截断/重试
- R004: 否定词或决策词候选 → 禁止静默替换
- R005: 左右侧冲突或缺失 → REVIEW
- R006: 卵巢大小不足两个数值 → BLOCK
- R007: 同一数字片段存在多种拆分 → REVIEW
- R008: 候选纠错涉及真实数字改变 → BLOCK
- R009: 内膜分型非A/B/C或冲突 → REVIEW
- R010: 回声性质冲突 → REVIEW
- R011: 卵泡数量与口述不一致 → REVIEW
- R012: LLM输出数值无source_span → 拒绝入库
- R013: LLM将candidate当作已确认 → 拒绝入库
- R014: 高风险词纠错 → REVIEW
- R015: 人工复核修改 → 回流候选池
"""
from dataclasses import dataclass, field
from typing import Optional, Any
import re


@dataclass
class RiskCheckResult:
    """风险检查结果"""
    passed: bool = True  # 是否通过风险检查
    blocked: bool = False  # 是否被阻断
    warnings: list[str] = field(default_factory=list)
    risk_items: list[dict] = field(default_factory=list)  # 检测到的风险项
    actions: list[dict] = field(default_factory=list)  # 建议的处理动作


@dataclass
class RiskRule:
    """风险拦截规则"""
    rule_id: str
    name: str
    description: str
    severity: str  # medium / high / highest
    action: str  # BLOCK / REVIEW / WARN
    enabled: bool = True


# ========== 风险拦截规则定义 ==========

RISK_RULES: list[RiskRule] = [
    RiskRule("R001", "ASR状态异常", "ASR状态非成功或文本为空",
             severity="highest", action="BLOCK"),
    RiskRule("R002", "循环重复输出", "同一8字以上片段连续重复≥3次",
             severity="high", action="REVIEW"),
    RiskRule("R003", "异常超长输出", "标准化后长度超过同批中位数3倍",
             severity="high", action="REVIEW"),
    RiskRule("R004", "否定词/决策词", "出现否定词或临床决策词候选",
             severity="highest", action="REVIEW"),
    RiskRule("R005", "左右侧冲突", "左右侧触发词冲突或缺失",
             severity="highest", action="REVIEW"),
    RiskRule("R006", "卵巢尺寸不完整", "卵巢大小不足两个数值",
             severity="highest", action="BLOCK"),
    RiskRule("R007", "数字边界不确定", "同一数字片段存在两种以上合理拆分",
             severity="highest", action="REVIEW"),
    RiskRule("R008", "真实数字改变", "候选纠错涉及真实数字改变",
             severity="highest", action="BLOCK"),
    RiskRule("R009", "内膜分型不确定", "内膜分型非A/B/C或模型间冲突",
             severity="highest", action="REVIEW"),
    RiskRule("R010", "回声性质冲突", "无回声与有/强/稍高回声同时指向同一对象",
             severity="highest", action="REVIEW"),
    RiskRule("R011", "卵泡数量不一致", "提取卵泡数量与口述数量不一致",
             severity="medium", action="REVIEW"),
    RiskRule("R012", "数值来源不明", "LLM输出数值无source_span",
             severity="highest", action="BLOCK"),
    RiskRule("R013", "候选被误确认", "LLM将candidate候选直接当作已确认事实",
             severity="highest", action="BLOCK"),
    RiskRule("R014", "高风险词纠错", "血糖/移植/麻醉/冻胚胎等高风险词纠错",
             severity="high", action="REVIEW"),
    RiskRule("R015", "人工修改回流", "人工复核修改了最终字段",
             severity="medium", action="REVIEW"),
    RiskRule("R016", "卵泡尺寸超常规", "卵泡直径超过常规上限 40mm，需人工复核",
             severity="high", action="REVIEW"),
    RiskRule("R017", "卵巢单维尺寸偏小", "卵巢任一维小于常规下限 10mm，需人工复核",
             severity="high", action="REVIEW"),
    RiskRule("R019", "卵泡格式异常", "卵泡数值不符合 n.m 格式，需人工复核",
             severity="high", action="REVIEW"),
    RiskRule("R020", "文本不可唯一恢复", "ASR 文本与人工结果之间不存在确定性文本转换证据，需回听",
             severity="highest", action="BLOCK"),
]

# 否定词列表
NEGATION_WORDS = ["无", "未见", "不", "没有", "取消", "未", "没"]

# 高风险决策词
HIGH_RISK_WORDS = ["血糖", "移植", "取消移植", "麻醉", "冻胚胎", "冻卵", "取卵"]

# 回声属性词
ECHO_KEYWORDS = ["无回声", "有回声", "强回声", "稍高回声", "回声欠均"]


class RiskInterceptor:
    """风险拦截器"""

    def __init__(self):
        self.risk_items: list[dict] = []
        self.warnings: list[str] = []
        self.actions: list[dict] = []

    def check_all(
        self,
        raw_text: str,
        normalized_text: str,
        conversions: list[dict],
        fields: dict[str, Any],
        source_spans: list[dict],
    ) -> RiskCheckResult:
        """执行所有风险检查"""
        self.risk_items = []
        self.warnings = []
        self.actions = []

        # R001: ASR状态检查
        self._check_r001_empty_text(raw_text)

        # R002: 循环重复检查
        self._check_r002_repetition(normalized_text)

        # R004: 否定词/决策词检查
        self._check_r004_negation(conversions)

        # R005: 左右侧冲突检查
        self._check_r005_side_conflict(fields, normalized_text)

        # R006: 卵巢尺寸完整性检查
        self._check_r006_dimension_complete(fields)

        # R007: 数字边界检查
        self._check_r007_digit_boundary(normalized_text)

        # R008: 真实数字改变检查
        self._check_r008_number_change(conversions)

        # R009: 内膜分型检查
        self._check_r009_endometrium_type(fields)

        # R010: 回声性质冲突检查
        self._check_r010_echo_conflict(fields, normalized_text)

        # R014: 高风险词纠错检查
        self._check_r014_high_risk_words(conversions)

        # R016: 卵泡尺寸超常规检查
        self._check_r016_follicle_overrange(fields)

        # R017: 卵巢单维尺寸偏小检查
        self._check_r017_ovary_small_dimension(fields)

        # R019: 卵泡格式异常检查
        self._check_r019_follicle_format(fields)

        # R020: 文本不可唯一恢复检查（仅人工标记触发，不自动触发）
        self._check_r020_unrecoverable_text(raw_text, fields)

        # 判断是否通过
        blocked = any(item.get("action") == "BLOCK" for item in self.risk_items)
        passed = len(self.risk_items) == 0

        return RiskCheckResult(
            passed=passed,
            blocked=blocked,
            warnings=self.warnings,
            risk_items=self.risk_items,
            actions=self.actions,
        )

    def _add_risk(self, rule_id: str, message: str, action: str, severity: str, details: dict = None):
        """添加风险项"""
        self.risk_items.append({
            "rule_id": rule_id,
            "message": message,
            "action": action,
            "severity": severity,
            "details": details or {},
        })
        self.warnings.append(f"【{action}】{rule_id}: {message}")
        self.actions.append({
            "rule_id": rule_id,
            "action": action,
            "message": message,
        })

    def _check_r001_empty_text(self, raw_text: str):
        """R001: ASR状态非成功或文本为空"""
        if not raw_text or not raw_text.strip():
            self._add_risk(
                "R001", "ASR文本为空，无法处理",
                action="BLOCK", severity="highest"
            )

    def _check_r002_repetition(self, text: str):
        """R002: 同一片段连续重复≥3次"""
        if len(text) < 24:  # 8字 × 3次
            return

        # 查找连续重复
        for seg_len in range(8, len(text) // 3 + 1):
            for start in range(len(text) - seg_len * 3 + 1):
                segment = text[start:start + seg_len]
                repeats = 1
                pos = start + seg_len
                while pos + seg_len <= len(text) and text[pos:pos + seg_len] == segment:
                    repeats += 1
                    pos += seg_len

                if repeats >= 3:
                    self._add_risk(
                        "R002", f"检测到循环输出：'{segment}' 重复 {repeats} 次",
                        action="REVIEW", severity="high",
                        details={"segment": segment, "repeats": repeats, "start": start}
                    )
                    return  # 只报告第一个

    def _check_r004_negation(self, conversions: list[dict]):
        """R004: 否定词或决策词候选"""
        for conv in conversions:
            raw = conv.get("raw", "")
            converted = conv.get("converted", "")

            # 检查是否涉及否定词
            for neg in NEGATION_WORDS:
                if neg in raw or neg in converted:
                    if conv.get("action") in ("AUTO", "CANDIDATE"):
                        self._add_risk(
                            "R004", f"涉及否定词 '{neg}'：{raw} → {converted}",
                            action="REVIEW", severity="highest",
                            details={"negation": neg, "conversion": conv}
                        )
                        break

            # 检查是否涉及决策词
            for word in HIGH_RISK_WORDS:
                if word in raw or word in converted:
                    if conv.get("action") == "AUTO":
                        self._add_risk(
                            "R014", f"高风险决策词 '{word}' 被自动修改：{raw} → {converted}",
                            action="REVIEW", severity="high",
                            details={"word": word, "conversion": conv}
                        )
                        break

    def _check_r005_side_conflict(self, fields: dict, text: str):
        """R005: 左右侧冲突或缺失

        左右侧归属不可猜测：存在未归属卵巢/卵泡数据、出现"左右卵巢/左右侧"模糊表述，
        或卵巢数据存在但全文缺少任何侧别触发词时，输出 REVIEW 警示。
        """
        has_right = "right_ovary_size" in fields or "right_follicles" in fields
        has_left = "left_ovary_size" in fields or "left_follicles" in fields
        has_unassigned = (
            "unassigned_ovary_sizes" in fields
            or "unassigned_follicle_values" in fields
        )

        if not has_right and not has_left and not has_unassigned:
            # 没有检测到任何卵巢数据，不适用侧别归属检查
            return

        if has_unassigned:
            self._add_risk(
                "R005", "存在未归属的卵巢/卵泡数据，缺少明确左右侧，需人工复核",
                action="REVIEW", severity="highest",
                details={"unassigned_fields": [key for key in ("unassigned_ovary_sizes", "unassigned_follicle_values") if key in fields]}
            )
            return

        if re.search(r"左\s*右", text):
            self._add_risk(
                "R005", "左右侧表述不明确，无法确定数据归属，需人工复核",
                action="REVIEW", severity="highest",
                details={"text": text}
            )
            return

        if not re.search(r"[左右]|换边", text):
            self._add_risk(
                "R005", "缺少左右侧触发词，卵巢数据归属不明确，需人工复核",
                action="REVIEW", severity="highest",
                details={"text": text}
            )

    def _check_r006_dimension_complete(self, fields: dict):
        """R006: 卵巢大小不足两个数值 / 存在无法确认的维度（??×N）"""
        for field_code in ["right_ovary_size", "left_ovary_size"]:
            if field_code not in fields:
                continue
            size = str(fields[field_code])
            if "??" in size:
                self._add_risk(
                    "R006", f"卵巢尺寸存在无法确认的维度：{field_code}={size}，必须回听或人工确认",
                    action="BLOCK", severity="highest",
                    details={"field_code": field_code, "value": size}
                )
                continue
            # 检查是否包含两个数值
            if "×" not in size and "*" not in size:
                self._add_risk(
                    "R006", f"卵巢尺寸不完整：{field_code}={size}",
                    action="BLOCK", severity="highest",
                    details={"field_code": field_code, "value": size}
                )

    def _check_r007_digit_boundary(self, text: str):
        """R007: 同一数字片段存在两种以上合理拆分"""
        # 检查4位连续数字（可能有多种拆分方式）
        pattern = r'(\d{4})'
        for m in re.finditer(pattern, text):
            num = m.group(1)
            # 检查是否在卵巢大小上下文
            context = text[max(0, m.start() - 20):m.end() + 20]
            if "卵巢" in context or "大小" in context:
                # 4位数字可能有多种拆分
                self._add_risk(
                    "R007", f"4位数字 '{num}' 可能有多种拆分方式",
                    action="REVIEW", severity="highest",
                    details={"number": num, "position": m.start()}
                )

    def _check_r008_number_change(self, conversions: list[dict]):
        """R008: 候选纠错涉及真实数字改变"""
        for conv in conversions:
            raw = conv.get("raw", "")
            converted = conv.get("converted", "")

            # 检查是否是数字替换
            raw_nums = re.findall(r'\d+\.?\d*', raw)
            conv_nums = re.findall(r'\d+\.?\d*', converted)

            if raw_nums and conv_nums:
                # 如果数字内容发生变化（不是格式变化）
                if set(raw_nums) != set(conv_nums):
                    # 排除格式变化（如 "三九乘以三零" → "39×30"）
                    if not (len(raw_nums) == 2 and len(conv_nums) == 2):
                        self._add_risk(
                            "R008", f"真实数字可能被改变：{raw} → {converted}",
                            action="BLOCK", severity="highest",
                            details={"conversion": conv}
                        )

    def _check_r009_endometrium_type(self, fields: dict):
        """R009: 内膜分型非A/B/C或冲突"""
        if "endometrium_type" in fields:
            etype = fields["endometrium_type"]
            if etype and etype not in ["A型", "B型", "C型"]:
                self._add_risk(
                    "R009", f"内膜分型异常：{etype}",
                    action="REVIEW", severity="highest",
                    details={"type": etype}
                )

    def _check_r010_echo_conflict(self, fields: dict, text: str):
        """R010: 回声性质冲突"""
        findings = fields.get("ultrasound_findings", [])
        if not findings:
            return

        # 检查是否同时存在矛盾的回声描述
        echo_types = [f.get("type", "") for f in findings if isinstance(f, dict)]
        negated_echoes = [f.get("type", "") for f in findings if isinstance(f, dict) and f.get("negated")]

        # 如果有"无回声"和其他回声类型同时存在
        if "无回声" in echo_types:
            other_echoes = [e for e in echo_types if e != "无回声"]
            if other_echoes:
                self._add_risk(
                    "R010", f"回声性质冲突：同时存在 '无回声' 和 '{other_echoes[0]}'",
                    action="REVIEW", severity="highest",
                    details={"echo_types": echo_types}
                )

    def _check_r014_high_risk_words(self, conversions: list[dict]):
        """R014: 高风险词纠错"""
        for conv in conversions:
            raw = conv.get("raw", "")
            converted = conv.get("converted", "")

            for word in HIGH_RISK_WORDS:
                if word in raw or word in converted:
                    if conv.get("action") in ("AUTO", "CANDIDATE"):
                        self._add_risk(
                            "R014", f"高风险词 '{word}' 被修改：{raw} → {converted}",
                            action="REVIEW", severity="high",
                            details={"word": word, "conversion": conv}
                        )
                        break

    @staticmethod
    def _follicle_numbers(fields: dict) -> list[tuple[str, float]]:
        """从字段中提取各侧卵泡数值（兼容裸数值或 {size,count} 对象）。"""
        result: list[tuple[str, float]] = []
        for field_code in ("right_follicles", "left_follicles"):
            values = fields.get(field_code)
            if not isinstance(values, list):
                continue
            for item in values:
                if isinstance(item, dict):
                    item = item.get("size", item.get("value"))
                try:
                    value = float(item)
                except (TypeError, ValueError):
                    continue
                result.append((field_code, value))
        return result

    def _check_r016_follicle_overrange(self, fields: dict):
        """R016: 卵泡直径超过常规上限 40mm

        只提示复核，不阻断：超上限可能是真实异常（如囊肿样大卵泡），
        也可能是 ASR 或录入错误，不能静默丢弃。
        """
        for field_code, value in self._follicle_numbers(fields):
            if value > 40:
                self._add_risk(
                    "R016", f"卵泡直径 {value}mm 超过常规上限 40mm，需人工复核",
                    action="REVIEW", severity="high",
                    details={"field_code": field_code, "value": value}
                )

    def _check_r017_ovary_small_dimension(self, fields: dict):
        """R017: 卵巢任一单维小于常规下限 10mm

        只提示复核，不阻断；确认口径后可作为人工复核提示。
        """
        for field_code in ("right_ovary_size", "left_ovary_size"):
            size = fields.get(field_code)
            if not size:
                continue
            dims = re.findall(r"\d+(?:\.\d+)?", str(size))
            if len(dims) < 2:
                continue
            for dim_str in dims:
                try:
                    dim = float(dim_str)
                except ValueError:
                    continue
                if dim < 10:
                    self._add_risk(
                        "R017", f"卵巢单维尺寸 {dim}mm 小于常规下限 10mm，需人工复核",
                        action="REVIEW", severity="high",
                        details={"field_code": field_code, "value": str(size), "dimension": dim}
                    )
                    break

    def _check_r019_follicle_format(self, fields: dict):
        """R019: 卵泡数值不符合 n.m 格式（字段解析已写入 unparsed_follicle_values）。"""
        values = fields.get("unparsed_follicle_values")
        if not isinstance(values, list) or not values:
            return
        for item in values:
            raw_text = item.get("raw_text", "") if isinstance(item, dict) else str(item)
            side = item.get("side", "") if isinstance(item, dict) else ""
            self._add_risk(
                "R019", f"卵泡数值 '{raw_text}' 不符合 n.m 格式（{side}），需人工复核",
                action="REVIEW", severity="high",
                details={"raw_text": raw_text, "side": side}
            )

    def _check_r020_unrecoverable_text(self, raw_text: str, fields: dict):
        """R020: 文本不可唯一恢复。

        只由人工标记或明确 manual_review_required 候选触发（fields 中带
        manual_review_required=True 或文本含该标记），不得靠模型猜测自动触发。
        """
        manual_flag = fields.get("manual_review_required") if isinstance(fields, dict) else None
        flagged = bool(manual_flag) or "manual_review_required" in (raw_text or "")
        if not flagged:
            return
        self._add_risk(
            "R020", "ASR 文本与人工结果之间不存在确定性文本转换证据，必须回听确认",
            action="BLOCK", severity="highest",
            details={"raw_text": raw_text}
        )


def check_risks(
    raw_text: str,
    normalized_text: str,
    conversions: list[dict],
    fields: dict[str, Any],
    source_spans: list[dict],
) -> RiskCheckResult:
    """执行风险检查"""
    interceptor = RiskInterceptor()
    return interceptor.check_all(raw_text, normalized_text, conversions, fields, source_spans)
