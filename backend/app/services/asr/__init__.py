"""
ASR 抽象层与实现
"""
import os
import re
import httpx
from abc import ABC, abstractmethod
from urllib.parse import urlsplit
from loguru import logger
from app.config import settings


class BaseASR(ABC):
    """ASR 抽象基类"""

    @abstractmethod
    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        """转写音频文件为文字"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        ...


class LocalFunASR(BaseASR):
    """本地 FunASR 服务

    真实服务端点：
      - POST /v1/audio/transcriptions  (OpenAI 兼容，推荐)
      - POST /asr                     (完整功能，支持 hotwords)
      - GET  /health
    """

    def __init__(self, url: str = None):
        self.url = (url or settings.LOCAL_ASR_URL).rstrip("/")

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        # endpoint 在数据库中存的是完整 URL（如 http://host:port/v1/audio/transcriptions）
        # 直接使用即可，不再拼接路径
        url = self.url
        async with httpx.AsyncClient(timeout=600) as client:
            with open(audio_path, "rb") as f:
                filename = os.path.basename(audio_path)
                files = {"file": (filename, f, "audio/wav")}
                data = {"model": "sensevoice", "language": "zh", "spk": "false"}

                try:
                    resp = await client.post(url, files=files, data=data)
                except httpx.ConnectError as e:
                    logger.error(f"FunASR 服务不可达 ({url}): {e}")
                    raise RuntimeError(f"FunASR 服务 {url} 无法连接，请确认服务已启动") from e

                if resp.status_code >= 400:
                    logger.error(f"FunASR 返回 {resp.status_code}: {resp.text[:300]}")
                    resp.raise_for_status()

                result = resp.json()

            if isinstance(result, dict):
                return result.get("text") or result.get("transcript") or ""
            return ""

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.url}/health")
                return resp.status_code == 200
        except Exception:
            return False


class QwenASR(BaseASR):
    """本地 Qwen ASR 服务（OpenAI 兼容 /v1/audio/transcriptions）。"""

    def __init__(self, endpoint: str = "", model_name: str = "", params: dict | None = None):
        self.endpoint = (endpoint or "http://172.16.10.142:7100/v1/audio/transcriptions").rstrip("/")
        self.model_name = model_name or "/llm/audio/models/Qwen/Qwen3-ASR-1___7B/"
        self.params = params or {}

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        data = {
            "model": self.model_name,
            "language": self.params.get("language", "zh"),
            "response_format": self.params.get("response_format", "json"),
            "temperature": str(self.params.get("temperature", 0)),
        }
        prompt = self.params.get("prompt")
        if prompt:
            data["prompt"] = str(prompt)
        if hotwords:
            merged_prompt = "、".join([str(item) for item in hotwords if str(item).strip()])
            data["prompt"] = f"{data.get('prompt', '')}\n热词：{merged_prompt}".strip()

        async with httpx.AsyncClient(timeout=float(self.params.get("timeout", 600))) as client:
            with open(audio_path, "rb") as f:
                filename = os.path.basename(audio_path)
                files = {"file": (filename, f, "audio/wav")}
                try:
                    resp = await client.post(self.endpoint, files=files, data=data)
                except httpx.ConnectError as e:
                    logger.error(f"Qwen ASR 服务不可达 ({self.endpoint}): {e}")
                    raise RuntimeError(f"Qwen ASR 服务 {self.endpoint} 无法连接，请确认服务已启动") from e

        if resp.status_code >= 400:
            logger.error(f"Qwen ASR 返回 {resp.status_code}: {resp.text[:500]}")
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            result = resp.json()
            if isinstance(result, dict):
                text = (
                    result.get("text")
                    or result.get("transcript")
                    or result.get("content")
                    or result.get("result")
                    or ""
                )
                if not text and isinstance(result.get("choices"), list) and result["choices"]:
                    choice = result["choices"][0]
                    text = choice.get("text") or choice.get("message", {}).get("content") or ""
                return self._clean_text(str(text or ""))
        return self._clean_text(resp.text)

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = (text or "").strip()
        # 提取 <asr_text>...</asr_text> 标签内的内容
        m = re.search(r'<asr_text>(.*?)</asr_text>', cleaned, re.DOTALL)
        if m:
            cleaned = m.group(1)
        elif '<asr_text>' in cleaned:
            cleaned = cleaned.split('<asr_text>', 1)[1]
            if '</asr_text>' in cleaned:
                cleaned = cleaned.split('</asr_text>', 1)[0]
        # 过滤 "language chinese" 等前缀（大小写不敏感，支持冒号/空格等分隔符）
        cleaned = re.sub(r'^language\s*[:：]?\s*chinese\s*[:：]?\s*', '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    async def health_check(self) -> bool:
        try:
            parsed = urlsplit(self.endpoint)
            base = f"{parsed.scheme}://{parsed.netloc}"
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{base}/health")
                if resp.status_code == 200:
                    return True
                models_resp = await client.get(f"{base}/v1/models")
                return models_resp.status_code == 200
        except Exception:
            return False


class IFlytekASR(BaseASR):
    """讯飞在线 ASR（预留接口）"""

    def __init__(self, api_key: str, api_secret: str, endpoint: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret
        self.endpoint = endpoint

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        # TODO: 实现讯飞 ASR 调用
        raise NotImplementedError("讯飞 ASR 待实现")

    async def health_check(self) -> bool:
        return False


class TencentASR(BaseASR):
    """腾讯在线 ASR（预留接口）"""

    def __init__(self, api_key: str, api_secret: str, endpoint: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret
        self.endpoint = endpoint

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        # TODO: 实现腾讯 ASR 调用
        raise NotImplementedError("腾讯 ASR 待实现")

    async def health_check(self) -> bool:
        return False


def create_asr(provider: str, **kwargs) -> BaseASR:
    """工厂函数：根据 provider 创建 ASR 实例"""
    match provider:
        case "local":
            return LocalFunASR(url=kwargs.get("endpoint", settings.LOCAL_ASR_URL))
        case "qwen_asr" | "qwen-asr":
            return QwenASR(
                endpoint=kwargs.get("endpoint"),
                model_name=kwargs.get("model_name"),
                params=kwargs.get("params") or {},
            )
        case "mimo":
            from app.services.asr.mimo_asr import MiMoASR
            return MiMoASR(
                api_key=kwargs.get("api_key"),
                endpoint=kwargs.get("endpoint"),
                model_name=kwargs.get("model_name") or "mimo-v2.5-asr",
                params=kwargs.get("params") or {},
            )
        case "iflytek":
            return IFlytekASR(
                api_key=kwargs.get("api_key", ""),
                api_secret=kwargs.get("api_secret", ""),
                endpoint=kwargs.get("endpoint", ""),
            )
        case "iflytek_rtasr_llm" | "xfyun_rtasr_llm":
            from app.services.asr.iflytek_rtasr_llm import IFlytekRealtimeLLMASR
            params = kwargs.get("params") or {}
            return IFlytekRealtimeLLMASR(
                endpoint=kwargs.get("endpoint"),
                access_key_id=kwargs.get("api_key"),
                access_key_secret=kwargs.get("api_secret"),
                app_id=kwargs.get("secret_key") or params.get("app_id"),
                params=params,
            )
        case "tencent":
            return TencentASR(
                api_key=kwargs.get("api_key", ""),
                api_secret=kwargs.get("api_secret", ""),
                endpoint=kwargs.get("endpoint", ""),
            )
        case "tencent_speaker_ws" | "tencent_realtime_speaker":
            from app.services.asr.tencent_speaker_asr import TencentSpeakerASR
            params = kwargs.get("params") or {}
            return TencentSpeakerASR(
                endpoint=kwargs.get("endpoint"),
                secret_id=kwargs.get("api_key"),
                secret_key=kwargs.get("api_secret"),
                app_id=kwargs.get("secret_key") or params.get("app_id"),
                params=params,
            )
        case "volcengine":
            from app.services.asr.volcengine_asr import VolcengineBigModelASR
            params = kwargs.get("params") or {}
            return VolcengineBigModelASR(
                api_key=kwargs.get("api_key"),
                endpoint=kwargs.get("endpoint"),
                access_key=kwargs.get("api_secret"),  # api_secret 存的是 access_token
                secret_key=kwargs.get("secret_key"),  # 真正的签名密钥
                **params,
            )
        case _:
            raise ValueError(f"未知的 ASR provider: {provider}")
