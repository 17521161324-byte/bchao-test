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
    def __init__(self, api_key: str = None, endpoint: str = None, model_name: str = None, params: dict | None = None):
        self.api_key = api_key or os.environ.get("MIMO_API_KEY", "")
        self.endpoint = endpoint or "https://api.xiaomimimo.com/v1/chat/completions"
        self.model_name = model_name or "mimo-v2.5-asr"
        self.params = params or {}

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        """转写音频文件为文字"""
        if not self.api_key:
            raise RuntimeError("MiMo ASR 未配置 API Key")

        # 读取并编码音频
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        max_base64_mb = float(self.params.get("max_base64_mb") or 9.5)
        current_base64_mb = len(audio_base64.encode("utf-8")) / 1024 / 1024
        if current_base64_mb > max_base64_mb:
            raise RuntimeError(f"MiMo ASR 音频 base64 {current_base64_mb:.2f}MB 超过限制 {max_base64_mb}MB")

        # 检测 MIME 类型
        mime = "audio/wav" if audio_path.lower().endswith(".wav") else "audio/mpeg"
        language = self.params.get("language") or "zh"
        # MiMo ASR 官方接口不允许在 messages.content 中混入 text part。
        # 错误示例会返回: "ASR request must not include text parts; text prompt is injected by the gateway"。
        # 因此这里仅发送 input_audio；领域提示词/热词保留在模型配置中供后续 LLM 使用，不注入 ASR 请求。

        # 构造请求
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        body = {
            "model": self.model_name,
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
                "language": language
            }
        }
        if self.params.get("stream") is True:
            body["stream"] = True

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                if body.get("stream"):
                    text = await self._post_stream(client, headers, body)
                    if not text.strip():
                        raise RuntimeError("MiMo ASR 流式返回空文本")
                    return text

                resp = await client.post(self.endpoint, headers=headers, json=body)

                # 处理未授权等错误
                if resp.status_code == 401:
                    logger.error(f"MiMo ASR 认证失败: API Key 无效或过期")
                    raise RuntimeError("MiMo ASR 认证失败: API Key 无效或过期")

                resp.raise_for_status()
                result = resp.json()

            # 提取转写文本
            try:
                text = result["choices"][0]["message"]["content"]
                if not str(text or "").strip():
                    raise RuntimeError(f"MiMo ASR 返回空文本: {result}")
                return text
            except (KeyError, IndexError):
                logger.error(f"MiMo 响应解析失败: {result}")
                raise RuntimeError("MiMo ASR 响应解析失败")
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:500] if e.response is not None else str(e)
            logger.error(f"MiMo ASR 调用失败: {detail}")
            raise RuntimeError(f"MiMo ASR 调用失败: {detail}") from e
        except Exception as e:
            logger.error(f"MiMo ASR 未知错误: {e}")
            raise

    async def _post_stream(self, client: httpx.AsyncClient, headers: dict, body: dict) -> str:
        """解析 MiMo chat/completions stream 响应。"""
        chunks: list[str] = []
        async with client.stream("POST", self.endpoint, headers=headers, json=body) as resp:
            if resp.status_code == 401:
                raise RuntimeError("MiMo ASR 认证失败: API Key 无效或过期")
            if resp.status_code >= 400:
                detail = await resp.aread()
                raise RuntimeError(f"MiMo ASR 调用失败: {detail.decode('utf-8', errors='ignore')[:500]}")

            async for line in resp.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    logger.warning(f"MiMo ASR 流式片段无法解析: {data[:200]}")
                    continue
                choice = (payload.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                message = choice.get("message") or {}
                piece = delta.get("content") or message.get("content") or ""
                if piece:
                    chunks.append(str(piece))
        return "".join(chunks)

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
    def create(api_key: str = None, endpoint: str = None, model_name: str = None, params: dict | None = None) -> MiMoASR:
        return MiMoASR(api_key=api_key, endpoint=endpoint, model_name=model_name, params=params)
