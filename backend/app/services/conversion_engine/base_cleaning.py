"""基础清洗模块。

对应规则文档中的基础清洗阶段，处理：
- 删除无效 ASR 标签（language Chinese<asr_text> 等）
- 清除异常空格
- 识别连续重复片段并截断
- 恢复基础标点
"""
import re
from dataclasses import dataclass, field


@dataclass
class CleaningResult:
    text: str
    conversions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _remove_asr_tags(text: str) -> tuple[str, list[dict]]:
    """移除 ASR 输出伪标记（language Chinese<asr_text> 等）"""
    conversions = []
    cleaned = text

    # 移除所有 "language Chinese<asr_text>" 组合模式
    pattern = r'language\s*[:：]?\s*chinese\s*[:：]?\s*<asr_text>'
    matches = list(re.finditer(pattern, cleaned, flags=re.IGNORECASE))
    for m in reversed(matches):
        conversions.append({
            "rule_id": "B001",
            "raw": m.group(),
            "converted": "",
            "action": "AUTO",
            "category": "format",
            "start": m.start(),
            "end": m.end(),
        })
        cleaned = cleaned[:m.start()] + cleaned[m.end():]

    # 提取 <asr_text>...</asr_text> 闭合标签内的内容
    m = re.search(r'<asr_text>(.*?)</asr_text>', cleaned, re.DOTALL)
    if m:
        conversions.append({
            "rule_id": "B002",
            "raw": m.group(),
            "converted": m.group(1),
            "action": "AUTO",
            "category": "format",
            "start": m.start(),
            "end": m.end(),
        })
        cleaned = m.group(1)
    else:
        # 无闭合标签时，移除所有残留标记
        for tag in ['<asr_text>', '</asr_text>']:
            if tag in cleaned:
                idx = cleaned.find(tag)
                conversions.append({
                    "rule_id": "B002",
                    "raw": tag,
                    "converted": "",
                    "action": "AUTO",
                    "category": "format",
                    "start": idx,
                    "end": idx + len(tag),
                })
                cleaned = cleaned.replace(tag, '')

    # 兜底：过滤开头的 "language chinese" 前缀
    prefix_pattern = r'^language\s*[:：]?\s*chinese\s*[:：]?\s*'
    m = re.match(prefix_pattern, cleaned, flags=re.IGNORECASE)
    if m:
        conversions.append({
            "rule_id": "B003",
            "raw": m.group(),
            "converted": "",
            "action": "AUTO",
            "category": "format",
            "start": 0,
            "end": m.end(),
        })
        cleaned = cleaned[m.end():]

    return cleaned.strip(), conversions


def _remove_abnormal_spaces(text: str) -> tuple[str, list[dict]]:
    """清除异常空格（保留中文间的正常空格）"""
    conversions = []
    original = text

    # 移除中英文之间的多余空格
    cleaned = re.sub(r'([\u4e00-\u9fff])\s+([a-zA-Z0-9])', r'\1\2', text)
    cleaned = re.sub(r'([a-zA-Z0-9])\s+([\u4e00-\u9fff])', r'\1\2', cleaned)

    # 移除连续多个空格
    cleaned = re.sub(r' {2,}', ' ', cleaned)

    if cleaned != original:
        conversions.append({
            "rule_id": "B004",
            "raw": "异常空格",
            "converted": "已清理",
            "action": "AUTO",
            "category": "format",
        })

    return cleaned.strip(), conversions


def _truncate_repeated_segments(text: str, min_length: int = 8, repeat_count: int = 3) -> tuple[str, list[dict]]:
    """截断连续重复片段。

    规则 R002: 同一8字以上片段连续重复>=3次时，保留首次完整片段。
    """
    conversions = []
    warnings = []

    if len(text) < min_length * repeat_count:
        return text, conversions

    # 查找连续重复的片段
    for seg_len in range(min_length, len(text) // repeat_count + 1):
        for start in range(len(text) - seg_len * repeat_count + 1):
            segment = text[start:start + seg_len]
            repeats = 1
            pos = start + seg_len
            while pos + seg_len <= len(text) and text[pos:pos + seg_len] == segment:
                repeats += 1
                pos += seg_len

            if repeats >= repeat_count:
                # 保留首次片段，截断后续重复
                truncated = text[:start + seg_len] + text[pos:]
                conversions.append({
                    "rule_id": "R002",
                    "raw": text[start:pos],
                    "converted": segment,
                    "action": "AUTO",
                    "category": "noise",
                    "start": start,
                    "end": pos,
                    "notes": f"连续重复{repeats}次，已截断",
                })
                warnings.append(f"检测到循环输出，已截断 {repeats} 次重复")
                return truncated, conversions

    return text, conversions


def _restore_punctuation(text: str) -> tuple[str, list[dict]]:
    """恢复基础标点（在数值列表间添加逗号）"""
    conversions = []
    original = text

    # 在连续数值之间添加逗号（如 "15.2 17.7 4.7" → "15.2, 17.7, 4.7"）
    # 匹配：数字.数字 空格 数字.数字 的模式
    cleaned = re.sub(
        r'(\d+\.?\d*)\s+(\d+\.?\d*)',
        lambda m: f"{m.group(1)}，{m.group(2)}" if _is_follicle_context(text, m.start()) else m.group(0),
        text
    )

    if cleaned != original:
        conversions.append({
            "rule_id": "B005",
            "raw": "数值列表",
            "converted": "已添加标点",
            "action": "AUTO",
            "category": "format",
        })

    return cleaned, conversions


def _is_follicle_context(text: str, pos: int) -> bool:
    """判断位置是否在卵泡列表上下文中"""
    # 简单启发式：前后出现卵泡相关词汇
    context_start = max(0, pos - 50)
    context_end = min(len(text), pos + 50)
    context = text[context_start:context_end]
    keywords = ["卵泡", "大小", "左侧", "右侧", "卵巢"]
    return any(kw in context for kw in keywords)


def apply_base_cleaning(text: str) -> CleaningResult:
    """执行所有基础清洗步骤"""
    result = CleaningResult(text=text)

    # 步骤1: 移除 ASR 标签
    result.text, convs = _remove_asr_tags(result.text)
    result.conversions.extend(convs)

    # 步骤2: 清除异常空格
    result.text, convs = _remove_abnormal_spaces(result.text)
    result.conversions.extend(convs)

    # 步骤3: 截断重复片段
    result.text, convs = _truncate_repeated_segments(result.text)
    result.conversions.extend(convs)

    # 步骤4: 恢复标点
    result.text, convs = _restore_punctuation(result.text)
    result.conversions.extend(convs)

    return result
