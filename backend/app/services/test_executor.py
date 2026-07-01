"""
测试执行引擎
"""
import time
from loguru import logger
from app.services.asr import create_asr
from app.services.llm import create_llm
from app.services.parser import DEFAULT_PROMPT_TEMPLATE


class TestExecutor:
    """单条测试执行器"""

    async def execute(
        self,
        segs: list[dict],
        asr_provider: str,
        asr_config: dict,
        llm_provider: str | None = None,
        llm_config: dict | None = None,
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
        progress_callback=None,
    ) -> dict:
        """
        执行完整测试流程：
        1. 逐 seg ASR 转写
        2. 拼接全文
        3. LLM 后处理（可选）
        """
        start_time = time.time()
        result = {
            "asr_results": [],
            "full_transcript": "",
            "llm_raw_output": None,
            "structured_result": None,
            "summary_text": None,
            "duration_seconds": 0,
        }

        # === ASR 阶段 ===
        asr = create_asr(asr_provider, **asr_config)
        total = len(segs)

        for i, seg in enumerate(segs):
            if progress_callback:
                await progress_callback({
                    "stage": "asr",
                    "current": i + 1,
                    "total": total,
                    "seg_text": None,
                    "message": f"正在转写第 {i+1}/{total} 段...",
                })

            try:
                text = await asr.transcribe(seg["file_path"])
                result["asr_results"].append({
                    "seg_index": seg["seg_index"],
                    "text": text,
                    "duration": seg.get("duration", 0),
                })
                if progress_callback:
                    await progress_callback({
                        "stage": "asr",
                        "current": i + 1,
                        "total": total,
                        "seg_text": text,
                    })
            except Exception as e:
                logger.error(f"ASR 转写失败 seg {seg['seg_index']}: {e}")
                result["asr_results"].append({
                    "seg_index": seg["seg_index"],
                    "text": f"[转写失败: {str(e)}]",
                    "duration": 0,
                })

        # 拼接全文
        result["full_transcript"] = "\n".join(
            r["text"] for r in result["asr_results"]
        )

        # === LLM 阶段 ===
        if llm_provider and llm_config:
            if progress_callback:
                await progress_callback({
                    "stage": "llm",
                    "message": "LLM 正在提取结构化信息...",
                })
            try:
                llm = create_llm(llm_provider, **llm_config)
                prompt = prompt_template.format(transcript=result["full_transcript"])
                llm_resp = await llm.extract(result["full_transcript"], prompt)
                result["llm_raw_output"] = llm_resp.raw_text
                result["structured_result"] = llm_resp.structured
                result["summary_text"] = llm_resp.summary
            except Exception as e:
                logger.error(f"LLM 处理失败: {e}")
                result["llm_raw_output"] = f"[LLM 处理失败: {str(e)}]"

        result["duration_seconds"] = round(time.time() - start_time, 2)

        if progress_callback:
            await progress_callback({
                "stage": "complete",
                "message": "测试完成",
            })

        return result
