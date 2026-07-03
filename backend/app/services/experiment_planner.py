"""
实验任务规划与失效规则
"""
from typing import Optional


def changed_stage(before: dict, after: dict) -> Optional[str]:
    """
    判断配置变化影响的阶段。

    Returns:
        "asr" - ASR 模型或热词变化，需要重跑 ASR+LLM+评估
        "llm" - LLM 模型或提示词变化，只需重跑 LLM+评估
        None  - 无影响执行的变化
    """
    # Normalize hotwords for comparison (order-independent)
    before_hotwords = sorted(before.get("hotwords", []))
    after_hotsorted = sorted(after.get("hotwords", []))

    # ASR-related changes
    if before.get("asr_model_id") != after.get("asr_model_id"):
        return "asr"
    if before_hotwords != after_hotsorted:
        return "asr"

    # LLM-related changes
    if before.get("llm_model_id") != after.get("llm_model_id"):
        return "llm"
    if before.get("prompt_template") != after.get("prompt_template"):
        return "llm"

    return None


def task_pairs(patient_ids: list[int], combination_ids: list[int]) -> list[tuple[int, int]]:
    """
    生成患者 × 组合的笛卡尔积任务对。
    顺序：患者优先（patient-major）。
    """
    return [(pid, cid) for pid in patient_ids for cid in combination_ids]
