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
        asr_result = await self.execute_asr(
            segs, asr_provider, asr_config,
            hotwords=asr_config.get("hotwords"),
            progress_callback=progress_callback,
        )
        result["asr_results"] = asr_result["asr_results"]
        result["full_transcript"] = asr_result["full_transcript"]

        # === LLM 阶段 ===
        if llm_provider and llm_config:
            try:
                llm_result = await self.execute_llm(
                    transcript=result["full_transcript"],
                    llm_provider=llm_provider,
                    llm_config=llm_config,
                    prompt_template=prompt_template,
                    progress_callback=progress_callback,
                )
                result["llm_raw_output"] = llm_result["llm_raw_output"]
                result["structured_result"] = llm_result["structured_result"]
                result["summary_text"] = llm_result["summary_text"]
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

    async def execute_asr(
        self,
        segs: list[dict],
        asr_provider: str,
        asr_config: dict,
        hotwords: list[str] | None = None,
        progress_callback=None,
    ) -> dict:
        """执行 ASR 转写阶段"""
        asr = create_asr(asr_provider, **asr_config)
        asr_results = []
        total = len(segs)

        for index, seg in enumerate(segs):
            if progress_callback:
                await progress_callback({
                    "stage": "asr",
                    "current": index + 1,
                    "total": total,
                    "seg_text": None,
                    "message": f"正在转写第 {index+1}/{total} 段...",
                })
            try:
                text = await asr.transcribe(seg["file_path"], hotwords=hotwords)
                asr_results.append({
                    "seg_index": seg["seg_index"],
                    "text": text,
                    "duration": seg.get("duration", 0),
                })
                if progress_callback:
                    await progress_callback({
                        "stage": "asr",
                        "current": index + 1,
                        "total": total,
                        "seg_text": text,
                    })
            except Exception as e:
                logger.error(f"ASR 转写失败 seg {seg['seg_index']}: {e}")
                asr_results.append({
                    "seg_index": seg["seg_index"],
                    "text": f"[转写失败: {str(e)}]",
                    "duration": 0,
                })

        return {
            "asr_results": asr_results,
            "full_transcript": "\n".join(item["text"] for item in asr_results),
        }

    async def execute_llm(
        self,
        transcript: str,
        llm_provider: str,
        llm_config: dict,
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
        progress_callback=None,
    ) -> dict:
        """执行 LLM 后处理阶段"""
        if progress_callback:
            await progress_callback({
                "stage": "llm",
                "message": "LLM 正在提取结构化信息...",
            })
        llm = create_llm(llm_provider, **llm_config)
        # 不要使用 prompt_template.format(transcript=transcript)
        # 因为提示词模板里包含 JSON 示例花括号,会被当成格式占位符解析 (KeyError)
        # OpenAILLM.extract 内部已经用 replace("{transcript}", transcript) 安全替换
        response = await llm.extract(transcript, prompt_template)
        return {
            "llm_raw_output": response.raw_text,
            "structured_result": response.structured,
            "summary_text": response.summary,
        }
