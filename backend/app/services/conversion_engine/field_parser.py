"""字段解析模块（改造版：Task 8）。

对应规则文档 04_字段解析规则 (F001-F014)，本次改造（DeepSeek 计划 Task 8）：
- 禁止默认右侧：无明确侧别时写入 unassigned_ovary_sizes，不写 right_ovary_size
- 侧别切换（右边/左边/换边）立即结束前一侧数据段
- 卵巢大小完成状态按侧别保存（ovary_size_complete）
- 核心字段锁定（locked_fields），冲突触发 FIELD_VALUE_CONFLICT
- 卵泡格式校验（n.m 格式，不合规写入 unparsed_follicle_values）
- "20×19无回声"（无卵巢锚点）归超声备注，不解析为卵巢大小
"""
import re
from dataclasses import dataclass, field
from typing import Optional, Any

from app.services.conversion_pipeline.types import ParserState
from app.services.conversion_engine.context_inference import (
    collect_anonymous_ovary_groups,
    collect_fuzzy_ovary_inferences,
    collect_inferred_endometrium_pairs,
)
from app.services.conversion_engine.endometrium_type_rules import (
    collect_endometrium_type_rule_items,
)


@dataclass
class FieldParseResult:
    """字段解析结果"""
    fields: dict[str, Any] = field(default_factory=dict)  # 解析出的结构化字段
    warnings: list[str] = field(default_factory=list)
    source_spans: list[dict] = field(default_factory=list)  # 每个字段的来源追踪
    final_state: dict[str, Any] = field(default_factory=dict)  # P0-06：解析器真实最终状态
    transitions: list[dict] = field(default_factory=list)  # P0-06：状态机变迁轨迹
    rule_items: list[dict[str, Any]] = field(default_factory=list)  # M003/M006/M007 可观测规则记录


@dataclass
class ParsedField:
    """单个解析出的字段"""
    field_code: str
    value: Any
    raw_text: str
    start: int
    end: int
    confidence: float = 1.0
    warning: Optional[str] = None


# ========== 常量定义 ==========

# 内膜分型枚举
ENDOMETRIUM_TYPES = {"A型", "B型", "C型", "A", "B", "C"}

# 超声发现关键词
ULTRASOUND_KEYWORDS = [
    # 长表达必须排在短表达之前，避免“强回声包块”只截成“强回声”。
    "内膜上见多个强回声包块", "内膜中断见息肉体影", "内膜上见强回声包块",
    "连续性稍欠佳", "连续性欠佳", "管状无回声", "囊性无回声",
    "强回声包块", "息肉样回声", "息肉体影", "宫腔分离", "内膜中断",
    "回声欠均", "回声不均", "稍高回声", "强回声", "无回声",
    "囊肿", "窦卵泡",
]

# 操作关键词
PROCEDURE_KEYWORDS = [
    "取卵", "移植", "冻胚胎", "冻卵", "麻醉",
    "全麻", "局麻", "静脉麻醉", "取消移植",
]

# 医嘱关键词
ORDER_KEYWORDS = [
    "抽血", "空腹", "白带常规", "B超", "复诊", "打针",
]

# 噪声关键词
NOISE_KEYWORDS = [
    "门", "钱", "医生", "姓名", "闲聊", "嗯", "啊", "哦",
]

# 数字范围检查
RANGE_CHECKS = {
    "endometrium_thickness": (1, 30, "mm"),  # 内膜厚度 1-30mm
    "follicle_diameter": (2, 40, "mm"),       # 卵泡直径 2-40mm
    "ovary_dimension": (10, 100, "mm"),       # 卵巢尺寸 10-100mm/维
}

# 侧别词
EXPLICIT_RIGHT = ("右边", "右侧", "右卵巢")
EXPLICIT_LEFT = ("左边", "左侧", "左卵巢")
SWITCH_WORDS = ("换边", "放边", "另一边")

# 卵泡有效格式：一位或两位整数 + 一位小数（13.8 / 9.6 / 15.0）
VALID_FOLLICLE_PATTERN = re.compile(r"(?<!\d)(\d{1,2}\.\d)(?!\d)")

# 卵巢大小尺寸（阿拉伯数字）
SIZE_PATTERN = re.compile(r'(\d+\.?\d*)\s*[×xX\*]\s*(\d+\.?\d*)')

# 卵巢大小缺失首维（??×38，P0-09）：显式未知标记，不伪装成正常数值
UNKNOWN_DIMENSION_PATTERN = re.compile(r'\?\?\s*[×xX\*]\s*(\d+\.?\d*)')

# 卵巢大小尺寸（中文数字：二零乘以幺九）
CN_DIMENSION_PATTERN = re.compile(
    r'([零一二三四五六七八九幺两]{2,4})乘以([零一二三四五六七八九幺两]{2,4})'
)

CN_DIGIT_MAP = {
    "零": "0", "一": "1", "幺": "1", "二": "2", "两": "2",
    "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
}


def _cn_digits_to_int(text: str) -> int | None:
    chars: list[str] = []
    for char in text:
        if char not in CN_DIGIT_MAP:
            return None
        chars.append(CN_DIGIT_MAP[char])
    return int("".join(chars)) if chars else None


class FieldParser:
    """字段解析器"""

    def __init__(self):
        self.state = ParserState()
        self.parsed_fields: list[ParsedField] = []
        self.warnings: list[str] = []
        self.source_spans: list[dict] = []
        self.transitions: list[dict] = []  # P0-06：状态机变迁轨迹
        self.unassigned_ovary_sizes: list[dict] = []
        self.unparsed_follicle_values: list[dict] = []
        self.incomplete_ovary_fields: list[str] = []  # P0-09：??×N 侧别字段码
        self.review_fields: list[str] = []  # P0-02：S012 缺“型”后缀反推的内膜字段（REVIEW）
        self.fuzzy_ovary_inferences: dict[int, Any] = {}
        self.anonymous_ovary_groups: dict[int, Any] = {}
        self.inferred_endometrium_pairs: dict[int, Any] = {}
        self.endometrium_type_items: dict[int, Any] = {}
        self.field_rule_items: list[dict[str, Any]] = []

    def parse(self, text: str) -> FieldParseResult:
        """解析文本，提取结构化字段"""
        self.parsed_fields = []
        self.warnings = []
        self.source_spans = []
        self.transitions = []
        self.state = ParserState()
        self.unassigned_ovary_sizes = []
        self.unparsed_follicle_values = []
        self.incomplete_ovary_fields = []
        self.review_fields = []
        self.fuzzy_ovary_inferences = {item.start: item for item in collect_fuzzy_ovary_inferences(text)}
        self.anonymous_ovary_groups = {item.start: item for item in collect_anonymous_ovary_groups(text)}
        self.inferred_endometrium_pairs = {item.start: item for item in collect_inferred_endometrium_pairs(text)}
        type_rule_items = collect_endometrium_type_rule_items(text)
        self.endometrium_type_items = {
            item.start: item for item in type_rule_items if item.converted and item.rule_id in {"M003", "M006"}
        }
        self.field_rule_items = [
            {
                "rule_id": item.rule_id,
                "rule_name": {
                    "M003": "标准内膜类型识别",
                    "M006": "多内膜类型冲突",
                    "M007": "疑似内膜类型近音词",
                }.get(item.rule_id, item.rule_id),
                "raw": item.raw,
                "converted": item.converted,
                "action": item.action,
                "category": "endometrium_type",
                "start": item.start,
                "end": item.end,
                "message": item.message,
                "evidence": item.evidence,
                "field_code": "endometrium_type",
            }
            for item in type_rule_items
        ]
        # P0-02：S012 无“型”后缀反推（如 14.8A）是 REVIEW 决策，追加到规则记录，
        # 使结果分级进入 REVIEW_REQUIRED 而不是 AUTO_ACCEPT。
        self.field_rule_items.extend([
            {
                "rule_id": item.rule_id,
                "rule_name": "数值+A/B/C型反推内膜段",
                "raw": item.raw_text,
                "converted": item.endometrium_type,
                "action": item.action,
                "category": "endometrium_type",
                "start": item.start,
                "end": item.end,
                "message": "内膜厚度数值后紧跟无“型”后缀的A/B/C，疑似内膜类型，需人工确认",
                "evidence": item.evidence,
                "field_code": "endometrium_type",
            }
            for item in self.inferred_endometrium_pairs.values()
            if item.action == "REVIEW"
        ])
        for item in type_rule_items:
            if item.action == "REVIEW":
                self.warnings.append(f"{item.rule_id}: {item.message}；{item.evidence}")

        # 按顺序扫描文本
        pos = 0
        while pos < len(text):
            # 跳过候选标记（兼容旧标记遗留）
            if text[pos:pos + 1] == "【":
                end_bracket = text.find("】", pos)
                if end_bracket != -1:
                    pos = end_bracket + 1
                    continue

            # S012：其他文本中出现标准“几点几 + A/B/C型”，从该数值处建立内膜段。
            # P0-02：缺少“型”后缀的“几点几 + A/B/C”（如 14.8A）动作为 REVIEW，
            # 只生成内膜厚度+内膜类型候选，不自动确认。
            inferred_endo = self.inferred_endometrium_pairs.get(pos)
            if inferred_endo:
                self._register_field(ParsedField(
                    field_code="endometrium_thickness",
                    value=inferred_endo.thickness, raw_text=inferred_endo.raw_text,
                    start=inferred_endo.start, end=inferred_endo.end,
                    confidence=0.98,
                ))
                self._register_field(ParsedField(
                    field_code="endometrium_type",
                    value=inferred_endo.endometrium_type, raw_text=inferred_endo.raw_text,
                    start=inferred_endo.start, end=inferred_endo.end,
                    confidence=0.98,
                ))
                if inferred_endo.action == "REVIEW":
                    # P0-02：缺少“型”后缀只能 REVIEW，登记 field_status 供前端与分级使用。
                    self.review_fields.extend(["endometrium_thickness", "endometrium_type"])
                self.warnings.append(f"S012: {inferred_endo.evidence}")
                pos = inferred_endo.end
                continue

            # C006/C007 + S006/S011：近似词只做候选，侧别由全文组合判断。
            fuzzy = self.fuzzy_ovary_inferences.get(pos)
            if fuzzy:
                if fuzzy.side in ("LEFT", "RIGHT"):
                    self._apply_side(fuzzy.side, text, pos, trigger=f"{fuzzy.rule_id}:{fuzzy.term}")
                    self.warnings.append(
                        f"{fuzzy.rule_id}: {fuzzy.term} → {'右' if fuzzy.side == 'RIGHT' else '左'}卵巢大小（上下文推断，需复核）"
                    )
                    field = self._parse_ovary_size(text, pos)
                    if field:
                        field.warning = "侧别来自上下文组合判定，需人工复核"
                        self._register_field(field)
                        pos = field.end
                        continue
                pos = fuzzy.end
                continue

            # S010：匿名尺寸/卵泡组 + 后置明确侧别，反推为另一侧业务段。
            anonymous = self.anonymous_ovary_groups.get(pos)
            if anonymous:
                self._apply_side(anonymous.side, text, pos, trigger="S010:匿名测量组反推")
                self.warnings.append(f"S010: {anonymous.evidence}（需复核）")
                field = self._parse_ovary_size(text, pos)
                if field:
                    field.warning = "侧别来自后置明确侧别反推，需人工复核"
                    self._register_field(field)
                    pos = field.end
                    continue

            # F003/F004: 解析卵巢大小（优先于侧别检测）
            # 检查当前位置是否以"卵巢大小"或"右/左卵巢大小"开头
            ovary_match = re.match(r'(右|左)?卵巢大小', text[pos:pos + 20])
            if ovary_match and ovary_match.start() == 0:
                # 带明确侧别词时更新侧别（结束前一侧数据段）
                if ovary_match.group(1) == "右":
                    self._apply_side("RIGHT", text, pos, trigger="右卵巢")
                elif ovary_match.group(1) == "左":
                    self._apply_side("LEFT", text, pos, trigger="左卵巢")
                field = self._parse_ovary_size(text, pos)
                if field:
                    self._register_field(field)
                    pos = field.end
                    continue
                pos += len(ovary_match.group(0))
                continue

            # F005/F006: 检测侧别切换（右边/左边/换边，后跟尺寸的情况）
            side = self._detect_side(text, pos)
            if side:
                side_len = self._side_word_len(text, pos)
                side_word = text[pos:pos + side_len]
                self._apply_side(side, text, pos, trigger=side_word)
                pos += side_len
                # 检查后面是否有尺寸（如 "右边39×30"）
                size_match = re.match(r'\s*(\d+\.?\d*)\s*[×xX\*]\s*(\d+\.?\d*)', text[pos:pos + 20])
                if size_match:
                    field = self._parse_ovary_size(text, pos)
                    if field:
                        self._register_field(field)
                        pos = field.end
                continue

            # 20×19无回声 / 二零乘以幺九无回声：无卵巢锚点时归备注
            anechoic = self._parse_anechoic_dimension(text, pos)
            if anechoic:
                self.parsed_fields.append(anechoic)
                pos = anechoic.end
                continue

            # F001: 解析内膜厚度
            if "内膜" in text[pos:pos + 10]:
                field = self._parse_endometrium_thickness(text, pos)
                if field:
                    self.parsed_fields.append(field)
                    pos = field.end
                    continue

            # F002: 解析内膜类型
            type_match = self._parse_endometrium_type(text, pos)
            if type_match:
                self.parsed_fields.append(type_match)
                pos = type_match.end
                continue

            # F009: 解析超声发现
            finding = self._parse_ultrasound_finding(text, pos)
            if finding:
                self.parsed_fields.append(finding)
                pos = finding.end
                continue

            # F010: 解析操作信息
            procedure = self._parse_procedure(text, pos)
            if procedure:
                self.parsed_fields.append(procedure)
                pos = procedure.end
                continue

            # F011: 解析医嘱
            order = self._parse_order(text, pos)
            if order:
                self.parsed_fields.append(order)
                pos = order.end
                continue

            # F007/F008: 解析卵泡数值（需明确侧别且该侧卵巢大小已完成）
            follicle = self._parse_follicle_value(text, pos)
            if follicle:
                self.parsed_fields.append(follicle)
                pos = follicle.end
                continue

            pos += 1

        # 整理结果
        return self._build_result()

    def _track_state(self, position: int, trigger: str, before: dict, after: dict) -> None:
        """P0-06：状态发生变化时记录变迁 {position, trigger, before, after}。"""
        if before != after:
            self.transitions.append({
                "position": position,
                "trigger": trigger,
                "before": before,
                "after": after,
            })

    def _apply_side(self, side: str, text: str, pos: int, trigger: str = "") -> None:
        """应用侧别：出现新侧别后结束前一侧数据段。"""
        before = self.state.to_dict()
        previous = self.state.current_side
        if side == "UNKNOWN":
            # 换边但无当前侧：保持 UNKNOWN 并警示
            self.warnings.append("换边词出现但当前侧别未知，数据归属不明确")
            self.state.current_side = "UNKNOWN"
            self._track_state(pos, trigger or "换边", before, self.state.to_dict())
            return
        if previous != side:
            self.state.current_field = None
        self.state.current_side = side
        self.state.last_explicit_side_position = pos
        self._track_state(pos, trigger or "侧别切换", before, self.state.to_dict())

    def _detect_side(self, text: str, pos: int) -> Optional[str]:
        """F005/F006: 检测侧别切换"""
        remaining = text[pos:]
        for word in EXPLICIT_RIGHT:
            if remaining.startswith(word):
                return "RIGHT"
        for word in EXPLICIT_LEFT:
            if remaining.startswith(word):
                return "LEFT"
        for word in SWITCH_WORDS:
            if remaining.startswith(word):
                if self.state.current_side == "RIGHT":
                    return "LEFT"
                if self.state.current_side == "LEFT":
                    return "RIGHT"
                return "UNKNOWN"
        return None

    def _side_word_len(self, text: str, pos: int) -> int:
        remaining = text[pos:]
        for word in (*EXPLICIT_RIGHT, *EXPLICIT_LEFT, *SWITCH_WORDS):
            if remaining.startswith(word):
                return len(word)
        return 0

    def _register_field(self, field: ParsedField) -> None:
        """注册字段：核心锚点字段锁定，冲突触发 FIELD_VALUE_CONFLICT。"""
        if field.field_code in self.state.locked_fields:
            existing = next(
                (p.value for p in self.parsed_fields if p.field_code == field.field_code),
                None,
            )
            if existing is not None and str(existing) != str(field.value):
                self.warnings.append(
                    f"FIELD_VALUE_CONFLICT: {field.field_code} 已有 {existing}，本次 {field.value}"
                )
            return
        self.parsed_fields.append(field)
        if field.field_code in ("right_ovary_size", "left_ovary_size",
                                "endometrium_thickness", "endometrium_type"):
            before = self.state.to_dict()
            self.state.locked_fields.add(field.field_code)
            self._track_state(field.start, f"字段锁定 {field.field_code}", before, self.state.to_dict())

    def _parse_endometrium_thickness(self, text: str, pos: int) -> Optional[ParsedField]:
        """F001: 解析内膜厚度"""
        pattern = r'内膜\s*(\d+\.?\d*)'
        m = re.match(pattern, text[pos:])
        if not m:
            return None

        value_str = m.group(1)
        try:
            value = float(value_str)
        except ValueError:
            return None

        value_fmt = str(int(value)) if value == int(value) else value_str

        warning = None
        min_val, max_val, unit = RANGE_CHECKS["endometrium_thickness"]
        if value < min_val or value > max_val:
            warning = f"内膜厚度 {value_fmt}{unit} 超出工程范围 {min_val}-{max_val}{unit}"

        return ParsedField(
            field_code="endometrium_thickness",
            value=value,
            raw_text=m.group(),
            start=pos,
            end=pos + m.end(),
            warning=warning,
        )

    def _parse_endometrium_type(self, text: str, pos: int) -> Optional[ParsedField]:
        """F002/M003/M006: 仅解析内膜业务窗口中的标准A/B/C类型。"""
        item = self.endometrium_type_items.get(pos)
        if item is None or not item.converted:
            return None
        warning = "同一内膜窗口出现多个类型，需人工确认" if item.action == "REVIEW" else None
        return ParsedField(
            field_code="endometrium_type",
            value=item.converted,
            raw_text=item.raw,
            start=item.start,
            end=item.end,
            confidence=1.0 if item.action == "AUTO" else 0.7,
            warning=warning,
        )

    def _parse_ovary_size(self, text: str, pos: int) -> Optional[ParsedField]:
        """F003/F004: 解析卵巢大小。

        无明确侧别时：不写 right/left_ovary_size，记入 unassigned_ovary_sizes。
        ??×38（P0-09）：缺失首维显式标记，写入对应侧字段并登记 INCOMPLETE。
        """
        before = self.state.to_dict()
        if self.state.current_side not in ("LEFT", "RIGHT"):
            # 无侧别：记入未归属
            m = SIZE_PATTERN.search(text[pos:pos + 30])
            if not m:
                return None
            dim1_str, dim2_str = m.group(1), m.group(2)
            try:
                dim1, dim2 = float(dim1_str), float(dim2_str)
            except ValueError:
                return None
            value = f"{str(int(dim1)) if dim1 == int(dim1) else dim1_str}×" \
                    f"{str(int(dim2)) if dim2 == int(dim2) else dim2_str}"
            self.unassigned_ovary_sizes.append({
                "value": value,
                "raw_text": text[pos:pos + m.end()],
                "start": pos,
                "end": pos + m.end(),
            })
            return None

        field_code = "right_ovary_size" if self.state.current_side == "RIGHT" else "left_ovary_size"

        segment = text[pos:pos + 30]
        m = SIZE_PATTERN.search(segment)
        incomplete = False
        if not m:
            m = UNKNOWN_DIMENSION_PATTERN.search(segment)
            incomplete = True
        if not m:
            return None

        if incomplete:
            dim2_str = m.group(1)
            try:
                dim2 = float(dim2_str)
            except ValueError:
                return None
            dim2_fmt = str(int(dim2)) if dim2 == int(dim2) else dim2_str
            value = f"??×{dim2_fmt}"
            self.incomplete_ovary_fields.append(field_code)
            self.state.ovary_size_complete[self.state.current_side] = False
            self._track_state(pos, f"卵巢大小不完整 {field_code}", before, self.state.to_dict())
            return ParsedField(
                field_code=field_code,
                value=value,
                raw_text=segment[m.start():m.end()],
                start=pos + m.start(),
                end=pos + m.end(),
            )

        dim1_str = m.group(1)
        dim2_str = m.group(2)
        try:
            dim1 = float(dim1_str)
            dim2 = float(dim2_str)
        except ValueError:
            return None

        dim1_fmt = str(int(dim1)) if dim1 == int(dim1) else dim1_str
        dim2_fmt = str(int(dim2)) if dim2 == int(dim2) else dim2_str
        value = f"{dim1_fmt}×{dim2_fmt}"
        self.state.ovary_size_complete[self.state.current_side] = True
        self._track_state(pos, f"卵巢大小解析 {field_code}", before, self.state.to_dict())

        warning = None
        min_val, max_val, unit = RANGE_CHECKS["ovary_dimension"]
        if dim1 < min_val or dim1 > max_val or dim2 < min_val or dim2 > max_val:
            warning = f"卵巢尺寸 {value}{unit} 超出工程范围 {min_val}-{max_val}{unit}/维"

        return ParsedField(
            field_code=field_code,
            value=value,
            raw_text=segment[m.start():m.end()],
            start=pos + m.start(),
            end=pos + m.end(),
            warning=warning,
        )

    def _parse_anechoic_dimension(self, text: str, pos: int) -> Optional[ParsedField]:
        """20×19无回声 / 二零乘以幺九无回声：无卵巢锚点 → 超声备注。

        二维尺寸 + 紧邻"无回声/五回声"，且前方无"卵巢大小"锚点 → 整体作为备注候选，
        不解析为卵巢大小。
        """
        before_start = max(0, pos - 20)
        before = text[before_start:pos]
        if "卵巢大小" in before:
            return None
        remark_start = pos
        side_prefix = re.search(r"(?:左|右)卵巢(?:内|外)?\s*$", before)
        if side_prefix:
            remark_start = before_start + side_prefix.start()

        raw_size: str | None = None
        end: int | None = None

        m = SIZE_PATTERN.match(text[pos:pos + 20])
        if m:
            raw_size = m.group(0)
            end = pos + m.end()
        else:
            m2 = CN_DIMENSION_PATTERN.match(text[pos:pos + 20])
            if m2:
                left = _cn_digits_to_int(m2.group(1))
                right = _cn_digits_to_int(m2.group(2))
                if left is not None and right is not None:
                    raw_size = f"{left}×{right}"
                    end = pos + m2.end()

        if raw_size is None or end is None:
            return None

        after = text[end:end + 4]
        suffix = None
        for word in ("无回声", "五回声"):
            if after.startswith(word):
                suffix = word
                break
        if suffix is None:
            return None

        full_remark = text[remark_start:end] + suffix
        return ParsedField(
            field_code="remark",
            value=full_remark,
            raw_text=full_remark,
            start=remark_start,
            end=end + len(suffix),
        )

    def _parse_follicle_value(self, text: str, pos: int) -> Optional[ParsedField]:
        """F007/F008: 解析卵泡数值（n.m 格式校验）。"""
        if self.state.current_side not in ("LEFT", "RIGHT"):
            return None

        if not self.state.ovary_size_complete[self.state.current_side]:
            # 该侧卵巢大小未完成：可保留为未归属候选，不写入左右卵泡
            return None

        m = re.match(r'(\d+\.?\d+)', text[pos:])
        if not m:
            return None

        raw = m.group(1)

        # 格式校验：必须 n.m（13/138/13.82 等不合规 → 警示，不塞入正常卵泡）
        if not VALID_FOLLICLE_PATTERN.fullmatch(raw):
            self.unparsed_follicle_values.append({
                "side": self.state.current_side,
                "raw_text": raw,
                "warning_code": "FOLLICLE_FORMAT_INVALID",
            })
            return None

        try:
            value = float(raw)
        except ValueError:
            return None

        # 先保留超上限卵泡（如 >40mm 可能是真实异常或 ASR 误报），
        # 由风险拦截 R016 生成警示，避免静默丢弃掩盖真实录入问题。
        if value < 2 or value > 100:
            return None

        warning = None
        min_val, max_val, unit = RANGE_CHECKS["follicle_diameter"]
        if value > max_val:
            warning = f"卵泡直径 {value}{unit} 超出常规范围 {min_val}-{max_val}{unit}，需人工复核"

        field_code = "right_follicles" if self.state.current_side == "RIGHT" else "left_follicles"

        return ParsedField(
            field_code=field_code,
            value=value,
            raw_text=m.group(),
            start=pos,
            end=pos + m.end(),
            warning=warning,
        )

    def _parse_ultrasound_finding(self, text: str, pos: int) -> Optional[ParsedField]:
        """F009: 解析超声发现"""
        for keyword in ULTRASOUND_KEYWORDS:
            if text[pos:].startswith(keyword):
                prefix = text[max(0, pos - 5):pos]
                negated = any(neg in prefix for neg in ["未见", "无", "不"])

                value = {
                    "type": keyword,
                    "negated": negated,
                }

                return ParsedField(
                    field_code="remark",
                    value=keyword,
                    raw_text=keyword,
                    start=pos,
                    end=pos + len(keyword),
                )

        return None

    def _parse_procedure(self, text: str, pos: int) -> Optional[ParsedField]:
        """F010: 解析操作信息"""
        for keyword in PROCEDURE_KEYWORDS:
            if text[pos:].startswith(keyword):
                prefix = text[max(0, pos - 10):pos]
                modifier = None
                if "不" in prefix or "未" in prefix:
                    modifier = "not"
                elif "取消" in prefix:
                    modifier = "cancelled"

                value = {
                    "procedure": keyword,
                    "modifier": modifier,
                }

                return ParsedField(
                    field_code="procedure_info",
                    value=value,
                    raw_text=text[pos:pos + len(keyword)],
                    start=pos,
                    end=pos + len(keyword),
                )

        return None

    def _parse_order(self, text: str, pos: int) -> Optional[ParsedField]:
        """F011: 解析医嘱"""
        for keyword in ORDER_KEYWORDS:
            if text[pos:].startswith(keyword):
                return ParsedField(
                    field_code="followup_orders",
                    value=keyword,
                    raw_text=keyword,
                    start=pos,
                    end=pos + len(keyword),
                )

        return None

    def _build_result(self) -> FieldParseResult:
        """构建解析结果"""
        fields = {}
        for pf in self.parsed_fields:
            field_code = pf.field_code

            if field_code in ("right_follicles", "left_follicles"):
                if field_code not in fields:
                    fields[field_code] = []
                fields[field_code].append(pf.value)
            elif field_code == "remark":
                existing = str(fields.get("remark") or "").strip()
                current = str(pf.value or "").strip()
                if current and current not in existing:
                    fields["remark"] = f"{existing}；{current}" if existing else current
            elif field_code == "procedure_info":
                if field_code not in fields:
                    fields[field_code] = []
                fields[field_code].append(pf.value)
            elif field_code == "followup_orders":
                if field_code not in fields:
                    fields[field_code] = []
                fields[field_code].append(pf.value)
            else:
                fields[field_code] = pf.value

            if pf.warning:
                self.warnings.append(pf.warning)

            self.source_spans.append({
                "field_code": pf.field_code,
                "raw_text": pf.raw_text,
                "start": pf.start,
                "end": pf.end,
                "confidence": pf.confidence,
            })

        if self.unassigned_ovary_sizes:
            fields["unassigned_ovary_sizes"] = list(self.unassigned_ovary_sizes)
        if self.unparsed_follicle_values:
            fields["unparsed_follicle_values"] = list(self.unparsed_follicle_values)
        if self.incomplete_ovary_fields:
            # P0-09：缺失维度侧别登记 INCOMPLETE，供 R006 阻断
            fields["field_status"] = {
                code: "INCOMPLETE" for code in self.incomplete_ovary_fields
            }
        if self.review_fields:
            # P0-02：S012 缺“型”后缀反推的内膜字段标记 REVIEW，需人工确认
            status = dict(fields.get("field_status") or {})
            for code in self.review_fields:
                status[code] = "REVIEW"
            fields["field_status"] = status

        return FieldParseResult(
            fields=fields,
            warnings=self.warnings,
            source_spans=self.source_spans,
            final_state=self.state.to_dict(),
            transitions=self.transitions,
            rule_items=self.field_rule_items,
        )


def parse_fields(text: str) -> FieldParseResult:
    """解析文本，提取结构化字段"""
    parser = FieldParser()
    return parser.parse(text)
