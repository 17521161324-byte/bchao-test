"""字段解析模块。

对应规则文档 04_字段解析规则 (F001-F014)：
- F001: 内膜厚度 (endometrium_thickness)
- F002: 内膜类型 (endometrium_type)
- F003/F004: 卵巢大小 (right/left_ovary_size)
- F005/F006: 当前侧状态 (current_side)
- F007/F008: 卵泡列表 (right/left_follicles)
- F009: 超声发现 (ultrasound_findings)
- F010: 操作信息 (procedure_info)
- F011: 随访医嘱 (followup_orders)
- F012: 提及数量 (mentioned_count)
- F013: 噪声片段 (noise_segment)
- F014: 来源追踪 (source_span)

解析采用状态机模式，按文本顺序扫描，根据触发词切换解析状态。
"""
import re
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class FieldParseResult:
    """字段解析结果"""
    fields: dict[str, Any] = field(default_factory=dict)  # 解析出的结构化字段
    warnings: list[str] = field(default_factory=list)
    source_spans: list[dict] = field(default_factory=list)  # 每个字段的来源追踪


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
    "无回声", "强回声", "稍高回声", "回声欠均", "回声不均",
    "囊肿", "窦卵泡", "管状无回声", "连续性稍欠佳",
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


class FieldParser:
    """字段解析器"""

    def __init__(self):
        self.current_side: Optional[str] = None  # RIGHT / LEFT
        self.ovary_size_started: bool = False
        self.parsed_fields: list[ParsedField] = []
        self.warnings: list[str] = []
        self.source_spans: list[dict] = []

    def parse(self, text: str) -> FieldParseResult:
        """解析文本，提取结构化字段"""
        self.parsed_fields = []
        self.warnings = []
        self.source_spans = []
        self.current_side = None
        self.ovary_size_started = False

        # 按顺序扫描文本
        pos = 0
        while pos < len(text):
            # 跳过已处理的内容（如候选标记）
            if text[pos:pos + 1] == "【":
                # 跳过候选标记
                end_bracket = text.find("】", pos)
                if end_bracket != -1:
                    pos = end_bracket + 1
                    continue

            # F003/F004: 解析卵巢大小（优先于侧别检测）
            # 检查当前位置是否以"卵巢大小"或"右/左卵巢大小"开头
            ovary_match = re.match(r'(右|左)?卵巢大小', text[pos:pos + 20])
            if ovary_match and ovary_match.start() == 0:
                # 先检测侧别
                side = self._detect_side(text, pos)
                if side:
                    self.current_side = side
                field = self._parse_ovary_size(text, pos)
                if field:
                    self.parsed_fields.append(field)
                    pos = field.end
                    continue

            # F005/F006: 检测侧别切换（包括"右边/左边"后跟尺寸的情况）
            side = self._detect_side(text, pos)
            if side:
                self.current_side = side
                # 计算侧别关键词的长度
                side_match = re.match(r'(右边|右侧|右卵巢|左边|左侧|左卵巢|换边)', text[pos:pos + 10])
                side_len = len(side_match.group()) if side_match else 0
                pos += side_len
                # 检查后面是否有尺寸（如 "右边39×30"）
                size_match = re.match(r'\s*(\d+\.?\d*)\s*[×xX\*]\s*(\d+\.?\d*)', text[pos:pos + 20])
                if size_match:
                    field = self._parse_ovary_size(text, pos)
                    if field:
                        self.parsed_fields.append(field)
                        pos = field.end
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

            # F007/F008: 解析卵泡数值（在卵巢大小之后）
            if self.current_side and self.ovary_size_started:
                follicle = self._parse_follicle_value(text, pos)
                if follicle:
                    self.parsed_fields.append(follicle)
                    pos = follicle.end
                    continue

            pos += 1

        # 整理结果
        return self._build_result()

    def _detect_side(self, text: str, pos: int) -> Optional[str]:
        """F005/F006: 检测侧别切换"""
        remaining = text[pos:]

        # 右侧
        if re.match(r'(右边|右侧|右卵巢)', remaining):
            return "RIGHT"
        # 左侧
        if re.match(r'(左边|左侧|左卵巢)', remaining):
            return "LEFT"
        # 换边
        if re.match(r'换边', remaining):
            # 切换到另一侧
            return "LEFT" if self.current_side == "RIGHT" else "RIGHT"

        return None

    def _parse_endometrium_thickness(self, text: str, pos: int) -> Optional[ParsedField]:
        """F001: 解析内膜厚度"""
        # 匹配：内膜 + 数字（支持小数）
        pattern = r'内膜\s*(\d+\.?\d*)'
        m = re.match(pattern, text[pos:])
        if not m:
            return None

        value_str = m.group(1)
        try:
            value = float(value_str)
        except ValueError:
            return None

        # 保留原始格式
        value_fmt = str(int(value)) if value == int(value) else value_str

        # 范围检查
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
        """F002: 解析内膜类型"""
        # 匹配：A型/B型/C型 或 A级/B级/C级
        pattern = r'([ABC])[型级]'
        m = re.match(pattern, text[pos:])
        if not m:
            return None

        value = f"{m.group(1)}型"

        return ParsedField(
            field_code="endometrium_type",
            value=value,
            raw_text=m.group(),
            start=pos,
            end=pos + m.end(),
        )

    def _parse_ovary_size(self, text: str, pos: int) -> Optional[ParsedField]:
        """F003/F004: 解析卵巢大小"""
        # 确定是左侧还是右侧
        if not self.current_side:
            # 尝试从上下文推断
            context = text[max(0, pos - 20):pos + 30]
            if "右" in context:
                self.current_side = "RIGHT"
            elif "左" in context:
                self.current_side = "LEFT"
            else:
                self.current_side = "RIGHT"  # 默认右侧

        field_code = "right_ovary_size" if self.current_side == "RIGHT" else "left_ovary_size"

        # 匹配：X×Y 或 X*X
        pattern = r'(\d+\.?\d*)\s*[×xX\*]\s*(\d+\.?\d*)'
        m = re.search(pattern, text[pos:pos + 30])
        if not m:
            return None

        # 保留原始格式（如 39×30 而不是 39.0×30.0）
        dim1_str = m.group(1)
        dim2_str = m.group(2)
        try:
            dim1 = float(dim1_str)
            dim2 = float(dim2_str)
        except ValueError:
            return None

        # 格式化：整数不保留小数点
        dim1_fmt = str(int(dim1)) if dim1 == int(dim1) else dim1_str
        dim2_fmt = str(int(dim2)) if dim2 == int(dim2) else dim2_str
        value = f"{dim1_fmt}×{dim2_fmt}"
        self.ovary_size_started = True

        # 范围检查
        warning = None
        min_val, max_val, unit = RANGE_CHECKS["ovary_dimension"]
        if dim1 < min_val or dim1 > max_val or dim2 < min_val or dim2 > max_val:
            warning = f"卵巢尺寸 {value}{unit} 超出工程范围 {min_val}-{max_val}{unit}/维"

        return ParsedField(
            field_code=field_code,
            value=value,
            raw_text=text[pos:pos + m.end()],
            start=pos,
            end=pos + m.end(),
            warning=warning,
        )

    def _parse_follicle_value(self, text: str, pos: int) -> Optional[ParsedField]:
        """F007/F008: 解析卵泡数值"""
        # 匹配单个数字（卵泡直径）
        pattern = r'(\d+\.?\d+)'
        m = re.match(pattern, text[pos:])
        if not m:
            return None

        try:
            value = float(m.group(1))
        except ValueError:
            return None

        # 范围检查
        min_val, max_val, unit = RANGE_CHECKS["follicle_diameter"]
        if value < min_val or value > max_val:
            # 可能是噪声或异常值
            return None

        field_code = "right_follicles" if self.current_side == "RIGHT" else "left_follicles"

        return ParsedField(
            field_code=field_code,
            value=value,
            raw_text=m.group(),
            start=pos,
            end=pos + m.end(),
        )

    def _parse_ultrasound_finding(self, text: str, pos: int) -> Optional[ParsedField]:
        """F009: 解析超声发现"""
        for keyword in ULTRASOUND_KEYWORDS:
            if text[pos:].startswith(keyword):
                # 检查是否有否定词
                prefix = text[max(0, pos - 5):pos]
                negated = any(neg in prefix for neg in ["未见", "无", "不"])

                value = {
                    "type": keyword,
                    "negated": negated,
                }

                return ParsedField(
                    field_code="ultrasound_findings",
                    value=value,
                    raw_text=keyword,
                    start=pos,
                    end=pos + len(keyword),
                )

        return None

    def _parse_procedure(self, text: str, pos: int) -> Optional[ParsedField]:
        """F010: 解析操作信息"""
        for keyword in PROCEDURE_KEYWORDS:
            if text[pos:].startswith(keyword):
                # 检查是否有否定/取消修饰
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

            # 卵泡列表需要聚合
            if field_code in ("right_follicles", "left_follicles"):
                if field_code not in fields:
                    fields[field_code] = []
                fields[field_code].append(pf.value)
            elif field_code == "ultrasound_findings":
                if field_code not in fields:
                    fields[field_code] = []
                fields[field_code].append(pf.value)
            elif field_code == "procedure_info":
                if field_code not in fields:
                    fields[field_code] = []
                fields[field_code].append(pf.value)
            elif field_code == "followup_orders":
                if field_code not in fields:
                    fields[field_code] = []
                fields[field_code].append(pf.value)
            else:
                # 对于其他字段，保留最后一个值
                fields[field_code] = pf.value

            # 收集警告
            if pf.warning:
                self.warnings.append(pf.warning)

            # 收集来源追踪
            self.source_spans.append({
                "field_code": pf.field_code,
                "raw_text": pf.raw_text,
                "start": pf.start,
                "end": pf.end,
                "confidence": pf.confidence,
            })

        return FieldParseResult(
            fields=fields,
            warnings=self.warnings,
            source_spans=self.source_spans,
        )


def parse_fields(text: str) -> FieldParseResult:
    """解析文本，提取结构化字段"""
    parser = FieldParser()
    return parser.parse(text)
