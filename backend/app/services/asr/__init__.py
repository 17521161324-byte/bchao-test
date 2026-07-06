"""
ASR 抽象层与实现
"""
import os
import httpx
from abc import ABC, abstractmethod
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
        case "mimo":
            from app.services.asr.mimo_asr import MiMoASR
            return MiMoASR(api_key=kwargs.get("api_key"), endpoint=kwargs.get("endpoint"))
        case "iflytek":
            return IFlytekASR(
                api_key=kwargs.get("api_key", ""),
                api_secret=kwargs.get("api_secret", ""),
                endpoint=kwargs.get("endpoint", ""),
            )
        case "tencent":
            return TencentASR(
                api_key=kwargs.get("api_key", ""),
                api_secret=kwargs.get("api_secret", ""),
                endpoint=kwargs.get("endpoint", ""),
            )
        case "volcengine":
            from app.services.asr.volcengine_asr import VolcengineBigModelASR
            return VolcengineBigModelASR(
                api_key=kwargs.get("api_key"),
                endpoint=kwargs.get("endpoint"),
                access_key=kwargs.get("api_secret"),  # api_secret 存的是 access_token
                secret_key=kwargs.get("secret_key"),  # 真正的签名密钥
            )
        case _:
            raise ValueError(f"未知的 ASR provider: {provider}")
