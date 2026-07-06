"""
MiMo 在线 ASR 服务对接
文档: https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/Speech-Recognition
"""
import os
import base64
import json
import httpx
from loguru import logger


class MiMoASR:
    def __init__(self, api_key: str = None, endpoint: str = None):
        self.api_key = api_key or os.environ.get("MIMO_API_KEY", "")
        self.endpoint = endpoint or "https://api.xiaomimimo.com/v1/chat/completions"

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        """转写音频文件为文字"""

        # 读取并编码音频
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        # 检测 MIME 类型
        mime = "audio/wav" if audio_path.lower().endswith(".wav") else "audio/mpeg"

        # 构造请求
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        body = {
            "model": "mimo-v2.5-asr",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": f"data:{mime};base64,{audio_base64}"
                            }
                        }
                    ]
                }
            ],
            "asr_options": {
                "language": "zh"
            }
        }

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(self.endpoint, headers=headers, json=body)

                # 处理未授权等错误
                if resp.status_code == 401:
                    logger.error(f"MiMo ASR 认证失败: API Key 无效或过期")
                    return ""

                resp.raise_for_status()
                result = resp.json()

            # 提取转写文本
            try:
                text = result["choices"][0]["message"]["content"]
                return text
            except (KeyError, IndexError):
                logger.error(f"MiMo 响应解析失败: {result}")
                return ""
        except httpx.HTTPStatusError as e:
            logger.error(f"MiMo ASR 调用失败: {e}")
            return ""
        except Exception as e:
            logger.error(f"MiMo ASR 未知错误: {e}")
            return ""

    async def health_check(self) -> bool:
        """健康检查 - 简单验证 API Key 是否有效"""
        try:
            headers = {"api-key": self.api_key, "Content-Type": "application/json"}
            body = {
                "model": "mimo-v2.5-asr",
                "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
                "max_tokens": 5
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self.endpoint, headers=headers, json=body)
                return resp.status_code == 200
        except Exception:
            return False


class MiMoASRFactory:
    @staticmethod
    def create(api_key: str = None, endpoint: str = None) -> MiMoASR:
        return MiMoASR(api_key=api_key, endpoint=endpoint)
