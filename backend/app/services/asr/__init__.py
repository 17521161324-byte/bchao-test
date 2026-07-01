"""
ASR 抽象层与实现
"""
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
    """本地 FunASR 服务"""

    def __init__(self, url: str = None):
        self.url = url or settings.LOCAL_ASR_URL

    async def transcribe(self, audio_path: str, hotwords: list[str] | None = None) -> str:
        async with httpx.AsyncClient(timeout=300) as client:
            with open(audio_path, "rb") as f:
                files = {"file": (audio_path.split("/")[-1], f, "audio/wav")}
                resp = await client.post(f"{self.url}/transcribe", files=files)
            resp.raise_for_status()
            data = resp.json()
            return data.get("transcript", "")

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
        case _:
            raise ValueError(f"未知的 ASR provider: {provider}")
