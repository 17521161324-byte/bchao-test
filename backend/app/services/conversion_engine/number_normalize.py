"""数字标准化模块。

对应规则文档 03_数字标准化规则 (N001-N016)：
- N001: 中文小数转阿拉伯数字
- N002: 幺作为数字1
- N003: 乘法连接词统一
- N004: 单位统一
- N005: 内膜分型格式化
- N006/N007: 4位连续尺寸候选拆分
- N008: 尺寸首维与次维跨片段合并
- N009: 异常小数点插入候选
- N010: 连续小数列表切分
- N011: 重复数值计数保留
- N012: 数值列表标点恢复
- N013: 内膜厚度工程范围检查
- N014: 卵泡直径工程范围检查
- N015: 卵巢尺寸完整性检查
- N016: 数字不可由LLM新增
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.conversion_engine.endometrium_type_rules import collect_endometrium_type_rule_items


@dataclass
class NumberResult:
    text: str
    conversions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# 中文数字映射
CHINESE_DIGITS = {
    '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
    '幺': 1,  # N002: 幺作为数字1
}

CHINESE_UNITS = {
    '十': 10, '百': 100, '千': 1000, '万': 10000,
}

# 小数点表达
DECIMAL_MARKERS = ['点', '。']


def _chinese_to_arabic(text: str) -> tuple[str, list[dict]]:
    """N001: 中文小数转阿拉伯数字（如 十七点八 → 17.8）

    仅处理明确的数值语境（如内膜厚度、卵泡值）。
    """
    conversions = []

    # 匹配中文数字+点+中文数字 的小数模式
    pattern = r'([零一二三四五六七八九十幺]+)(点|。)([零一二三四五六七八九十幺]+)'

    def replace_decimal(m):
        integer_part = _parse_chinese_number(m.group(1))
        decimal_part = m.group(3)
        # 将小数部分逐字转换
        decimal_str = ''
        for ch in decimal_part:
            if ch in CHINESE_DIGITS:
                decimal_str += str(CHINESE_DIGITS[ch])
            else:
                decimal_str += ch

        if integer_part is not None:
            result = f"{integer_part}.{decimal_str}"
            conversions.append({
                "rule_id": "N001",
                "raw": m.group(),
                "converted": result,
                "action": "AUTO",
                "category": "number_format",
                "start": m.start(),
                "end": m.end(),
            })
            return result
        return m.group()

    cleaned = re.sub(pattern, replace_decimal, text)
    return cleaned, conversions


def _parse_chinese_number(s: str) -> Optional[int]:
    """解析中文数字为整数（支持十几、几十几、几几等）"""
    if not s:
        return None

    # 简单情况：单个数字
    if len(s) == 1 and s in CHINESE_DIGITS:
        return CHINESE_DIGITS[s]

    # 两位数：几几（如 二一 → 21, 三九 → 39）
    if len(s) == 2:
        tens = CHINESE_DIGITS.get(s[0])
        ones = CHINESE_DIGITS.get(s[1])
        if tens is not None and ones is not None:
            return tens * 10 + ones

    # 十几 的情况
    if s.startswith('十'):
        rest = s[1:]
        if not rest:
            return 10
        digit = CHINESE_DIGITS.get(rest)
        if digit is not None:
            return 10 + digit
        return None

    # 几十几 的情况
    if '十' in s:
        parts = s.split('十')
        tens = CHINESE_DIGITS.get(parts[0])
        if tens is None:
            return None
        if len(parts) > 1 and parts[1]:
            ones = CHINESE_DIGITS.get(parts[1])
            if ones is not None:
                return tens * 10 + ones
        return tens * 10

    return None


def _normalize_yao(text: str) -> tuple[str, list[dict]]:
    """N002: 幺作为数字1（如 二幺 → 21）

    仅在数值列表/尺寸语境中生效。
    """
    conversions = []

    # 匹配包含"幺"的数值模式
    pattern = r'([零一二三四五六七八九十]+幺[零一二三四五六七八九十幺]*)'

    def replace_yao(m):
        raw = m.group()
        # 将幺替换为1后重新解析
        normalized = raw.replace('幺', '一')
        result = _parse_chinese_number(normalized)
        if result is not None:
            str_result = str(result)
            conversions.append({
                "rule_id": "N002",
                "raw": raw,
                "converted": str_result,
                "action": "AUTO",
                "category": "number_format",
                "start": m.start(),
                "end": m.end(),
            })
            return str_result
        return raw

    cleaned = re.sub(pattern, replace_yao, text)
    return cleaned, conversions


def _normalize_multiply_operator(text: str) -> tuple[str, list[dict]]:
    """N003: 乘法连接词统一（如 三九乘以三零 → 39×30）

    乘、乘以、叉、x、X、* 统一为 ×
    """
    conversions = []

    # 先处理中文数字的乘法表达
    pattern = r'([零一二三四五六七八九十幺]+)(乘以?|叉|[xX\*])([零一二三四五六七八九十幺]+)'

    def replace_multiply(m):
        raw = m.group()
        num1 = _parse_chinese_number(m.group(1))
        right_raw = m.group(3)
        protected_suffix = ""
        # 医学词步骤已把“五回声”登记为高风险候选。数字转换不得把
        # “五八乘以三八五回声”吞成 58×385；最后一个“五”属于“五回声”。
        if right_raw.endswith("五") and text[m.end():].startswith("回声") and len(right_raw) > 2:
            right_raw = right_raw[:-1]
            protected_suffix = "五"
        num2 = _parse_chinese_number(right_raw)

        if num1 is not None and num2 is not None:
            result = f"{num1}×{num2}{protected_suffix}"
            conversions.append({
                "rule_id": "N003",
                "raw": raw,
                "converted": result,
                "action": "AUTO",
                "category": "size_format",
                "start": m.start(),
                "end": m.end(),
            })
            return result
        return raw

    cleaned = re.sub(pattern, replace_multiply, text)

    # 再处理阿拉伯数字的乘法表达
    pattern2 = r'(\d+)\s*(乘以?|叉|[xX\*])\s*(\d+)'

    def replace_multiply2(m):
        raw = m.group()
        result = f"{m.group(1)}×{m.group(3)}"
        if raw != result:
            conversions.append({
                "rule_id": "N003",
                "raw": raw,
                "converted": result,
                "action": "AUTO",
                "category": "size_format",
                "start": m.start(),
                "end": m.end(),
            })
        return result

    cleaned = re.sub(pattern2, replace_multiply2, cleaned)
    return cleaned, conversions


def _normalize_unit(text: str) -> tuple[str, list[dict]]:
    """N004: 单位统一（如 十二毫米 → 12 mm）"""
    conversions = []

    # 中文单位转英文
    unit_map = {
        '毫米': 'mm', '厘米': 'cm', '毫升': 'ml',
        'MM': 'mm', 'CM': 'cm', 'ML': 'ml',
    }

    for cn_unit, en_unit in unit_map.items():
        if cn_unit in text:
            # 匹配阿拉伯数字+单位
            pattern = r'(\d+)\s*' + re.escape(cn_unit)
            def replace_unit(m, eu=en_unit):
                result = f"{m.group(1)} {eu}"
                conversions.append({
                    "rule_id": "N004",
                    "raw": m.group(),
                    "converted": result,
                    "action": "AUTO",
                    "category": "unit_format",
                    "start": m.start(),
                    "end": m.end(),
                })
                return result
            text = re.sub(pattern, replace_unit, text)

            # 匹配中文数字+单位
            cn_num_pattern = r'([零一二三四五六七八九十]+)\s*' + re.escape(cn_unit)
            def replace_cn_unit(m, eu=en_unit):
                cn_num = m.group(1)
                arabic_num = _parse_chinese_number(cn_num)
                if arabic_num is not None:
                    result = f"{arabic_num} {eu}"
                    conversions.append({
                        "rule_id": "N004",
                        "raw": m.group(),
                        "converted": result,
                        "action": "AUTO",
                        "category": "unit_format",
                        "start": m.start(),
                        "end": m.end(),
                    })
                    return result
                return m.group()
            text = re.sub(cn_num_pattern, replace_cn_unit, text)

    return text, conversions


def _normalize_endometrium_type(text: str) -> tuple[str, list[dict]]:
    """N005: 仅在内膜业务窗口内把A/B/C的型/形/性变体归一为“X型”。"""
    conversions: list[dict] = []
    replacements: list[tuple[int, int, str]] = []
    for item in collect_endometrium_type_rule_items(text):
        # 多类型冲突(M006)和疑似近音(M007)必须保留原文等待复核。
        if item.rule_id != "M003" or item.action != "AUTO" or not item.converted:
            continue
        if item.raw == item.converted:
            continue
        conversions.append({
            "rule_id": "N005",
            "raw": item.raw,
            "converted": item.converted,
            "action": "AUTO",
            "category": "format",
            "start": item.start,
            "end": item.end,
            "notes": "只在内膜业务窗口内归一A/B/C型变体",
        })
        replacements.append((item.start, item.end, item.converted))

    cleaned = text
    for start, end, converted in sorted(replacements, reverse=True):
        cleaned = cleaned[:start] + converted + cleaned[end:]
    return cleaned, conversions


def _split_4digit_dimension(text: str, scene: str) -> tuple[str, list[dict]]:
    """N006/N007: 4位连续尺寸候选拆分（如 六零三五 → 60×35）

    仅在紧跟卵巢大小后时生效，动作为 CANDIDATE。
    """
    conversions = []

    # 匹配4位连续数字（可能是中文或阿拉伯数字）
    # 先将中文数字转为阿拉伯数字
    chinese_4digit = r'([零一二三四五六七八九幺])([零一二三四五六七八九幺])([零一二三四五六七八九幺])([零一二三四五六七八九幺])'

    def split_dimension(m):
        raw = m.group()
        # 转换为阿拉伯数字
        digits = []
        for ch in m.groups():
            if ch in CHINESE_DIGITS:
                digits.append(str(CHINESE_DIGITS[ch]))
            else:
                return raw  # 无法转换，保持原样

        num_str = ''.join(digits)
        # 检查是否在卵巢大小上下文
        if _is_ovary_context(text, m.start()):
            result = f"{num_str[:2]}×{num_str[2:]}"
            conversions.append({
                "rule_id": "N006",
                "raw": raw,
                "converted": result,
                "action": "CANDIDATE",
                "category": "size_format",
                "start": m.start(),
                "end": m.end(),
                "confidence": 0.8,
                "risk_level": "medium",
                "notes": "4位连续数字，疑似卵巢尺寸，需确认",
            })
            # CANDIDATE 只记录候选，不覆盖当前有效文本。
            return raw
        return raw

    cleaned = re.sub(chinese_4digit, split_dimension, text)

    # 也处理阿拉伯数字的4位连续
    arabic_4digit = r'(?<!\d)(\d{4})(?!\d)'

    def split_arabic_4digit(m):
        raw = m.group()
        if _is_ovary_context(text, m.start()):
            result = f"{raw[:2]}×{raw[2:]}"
            conversions.append({
                "rule_id": "N007",
                "raw": raw,
                "converted": result,
                "action": "CANDIDATE",
                "category": "size_format",
                "start": m.start(),
                "end": m.end(),
                "confidence": 0.8,
                "risk_level": "medium",
            })
            # CANDIDATE 只记录候选，不覆盖当前有效文本。
            return raw
        return raw

    cleaned = re.sub(arabic_4digit, split_arabic_4digit, cleaned)

    return cleaned, conversions


def _is_ovary_context(text: str, pos: int) -> bool:
    """判断位置是否在卵巢大小上下文中"""
    context_start = max(0, pos - 30)
    context = text[context_start:pos]
    keywords = ["卵巢大小", "卵巢", "大小"]
    return any(kw in context for kw in keywords)


def _check_dimension_anomaly(text: str) -> tuple[str, list[dict]]:
    """N009: 异常小数点插入候选（如 三六乘一点三四 → 36×34）

    当尺寸表达中出现异常小数点时，标记为 REVIEW。
    """
    conversions = []

    # 匹配 X乘Y.Z 的异常模式
    pattern = r'(\d+)乘(\d+)\.(\d+)'

    def check_anomaly(m):
        raw = m.group()
        # 检查小数部分是否异常（如 1.34 在尺寸语境中不合理）
        decimal_part = float(f"{m.group(2)}.{m.group(3)}")
        if decimal_part > 100:  # 尺寸不应超过100mm
            result = f"{m.group(1)}×{m.group(2)}"
            conversions.append({
                "rule_id": "N009",
                "raw": raw,
                "converted": result,
                "action": "REVIEW",
                "category": "size_format",
                "start": m.start(),
                "end": m.end(),
                "risk_level": "highest",
                "notes": "异常小数点，疑似尺寸误识",
            })
            # REVIEW 只记录候选值，原文留给人工确认。
            return raw
        return raw

    cleaned = re.sub(pattern, check_anomaly, text)
    return cleaned, conversions


def _split_decimal_sequence(text: str) -> tuple[str, list[dict]]:
    """N010: 连续小数列表切分（如 11.09.48.8 → 11.0, 9.4, 8.8）"""
    conversions = []

    # 匹配连续小数点模式
    pattern = r'(\d+)\.(\d+)(?:\.(\d+))+'

    def split_sequence(m):
        raw = m.group()
        # 尝试合理切分
        numbers = re.findall(r'\d+\.?\d*', raw)
        if len(numbers) >= 2:
            result = ', '.join(numbers)
            conversions.append({
                "rule_id": "N010",
                "raw": raw,
                "converted": result,
                "action": "CANDIDATE",
                "category": "number_format",
                "start": m.start(),
                "end": m.end(),
                "confidence": 0.75,
                "risk_level": "medium",
            })
            # CANDIDATE 不修改当前有效文本。
            return raw
        return raw

    cleaned = re.sub(pattern, split_sequence, text)
    return cleaned, conversions


def _expand_count_notation(text: str) -> tuple[str, list[dict]]:
    """N011: 重复数值计数保留（如 12.7两个 → 12.7, 12.7）"""
    conversions = []

    # 匹配 数字+两个/三个 等
    pattern = r'(\d+\.?\d*)(两个|三个|四个|五个|六个|七个|八个|九个|十个)'

    count_map = {
        '两个': 2, '三个': 3, '四个': 4, '五个': 5,
        '六个': 6, '七个': 7, '八个': 8, '九个': 9, '十个': 10,
    }

    def expand_count(m):
        raw = m.group()
        number = m.group(1)
        count = count_map.get(m.group(2), 1)
        result = ', '.join([number] * count)
        conversions.append({
            "rule_id": "N011",
            "raw": raw,
            "converted": result,
            "action": "CANDIDATE",
            "category": "number_format",
            "start": m.start(),
            "end": m.end(),
            "confidence": 0.75,
            "risk_level": "medium",
            "notes": "仅作候选，不能覆盖原始列表",
        })
        # CANDIDATE 不修改当前有效文本。
        return raw

    cleaned = re.sub(pattern, expand_count, text)
    return cleaned, conversions


def _punctuate_numeric_list(text: str) -> tuple[str, list[dict]]:
    """N012: 数值列表标点恢复（如 15.2 17.7 4.7 → 15.2，17.7，4.7）"""
    conversions = []

    # 在卵泡列表上下文中，为连续数值添加逗号
    # 匹配：数字 空格 数字 的模式
    pattern = r'(\d+\.?\d*)\s+(\d+\.?\d*)(?=\s|$)'

    def punctuate(m):
        if _is_follicle_context(text, m.start()):
            result = f"{m.group(1)}，{m.group(2)}"
            if m.group() != result:
                conversions.append({
                    "rule_id": "N012",
                    "raw": m.group(),
                    "converted": result,
                    "action": "AUTO",
                    "category": "number_format",
                    "start": m.start(),
                    "end": m.end(),
                })
            return result
        return m.group()

    cleaned = re.sub(pattern, punctuate, text)
    return cleaned, conversions


def _is_follicle_context(text: str, pos: int) -> bool:
    """判断位置是否在卵泡列表上下文中"""
    context_start = max(0, pos - 50)
    context_end = min(len(text), pos + 50)
    context = text[context_start:context_end]
    keywords = ["卵泡", "大小", "左侧", "右侧", "卵巢"]
    return any(kw in context for kw in keywords)


def apply_number_normalize(text: str, scene: str = "follicle_ultrasound") -> NumberResult:
    """执行所有数字标准化步骤"""
    result = NumberResult(text=text)

    # N001: 中文小数转阿拉伯数字
    result.text, convs = _chinese_to_arabic(result.text)
    result.conversions.extend(convs)

    # N002: 幺作为数字1
    result.text, convs = _normalize_yao(result.text)
    result.conversions.extend(convs)

    # N003: 乘法连接词统一
    result.text, convs = _normalize_multiply_operator(result.text)
    result.conversions.extend(convs)

    # N004: 单位统一
    result.text, convs = _normalize_unit(result.text)
    result.conversions.extend(convs)

    # N005: 内膜分型格式化
    result.text, convs = _normalize_endometrium_type(result.text)
    result.conversions.extend(convs)

    # N006/N007: 4位连续尺寸候选拆分
    result.text, convs = _split_4digit_dimension(result.text, scene)
    result.conversions.extend(convs)

    # N009: 异常小数点插入候选
    result.text, convs = _check_dimension_anomaly(result.text)
    result.conversions.extend(convs)

    # N010: 连续小数列表切分
    result.text, convs = _split_decimal_sequence(result.text)
    result.conversions.extend(convs)

    # N011: 重复数值计数保留
    result.text, convs = _expand_count_notation(result.text)
    result.conversions.extend(convs)

    # N012: 数值列表标点恢复
    result.text, convs = _punctuate_numeric_list(result.text)
    result.conversions.extend(convs)

    return result
