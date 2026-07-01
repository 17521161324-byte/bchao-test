"""
LLM 抽象层与实现
"""
from abc import ABC, abstractmethod
from pydantic import BaseModel
from loguru import logger


class LLMResponse(BaseModel):
    raw_text: str
    structured: dict | None = None
    summary: str | None = None


class BaseLLM(ABC):
    """LLM 抽象基类"""

    @abstractmethod
    async def extract(self, transcript: str, prompt_template: str) -> LLMResponse:
        """从转写文本中提取结构化信息"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        ...


class IFlytekSpark(BaseLLM):
    """讯飞星火 LLM（预留接口）"""

    def __init__(self, api_key: str, model_name: str = "spark-v3.5", **kwargs):
        self.api_key = api_key
        self.model_name = model_name

    async def extract(self, transcript: str, prompt_template: str) -> LLMResponse:
        # TODO: 实现讯飞星火调用
        raise NotImplementedError("讯飞星火 LLM 待实现")

    async def health_check(self) -> bool:
        return False


class TencentHunyuan(BaseLLM):
    """腾讯混元 LLM（预留接口）"""

    def __init__(self, api_key: str, model_name: str = "hunyuan-standard", **kwargs):
        self.api_key = api_key
        self.model_name = model_name

    async def extract(self, transcript: str, prompt_template: str) -> LLMResponse:
        # TODO: 实现腾讯混元调用
        raise NotImplementedError("腾讯混元 LLM 待实现")

    async def health_check(self) -> bool:
        return False


class LocalLLM(BaseLLM):
    """本地 LLM（预留接口，后续部署）"""

    def __init__(self, endpoint: str, model_name: str = "", **kwargs):
        self.endpoint = endpoint
        self.model_name = model_name

    async def extract(self, transcript: str, prompt_template: str) -> LLMResponse:
        raise NotImplementedError("本地 LLM 待部署")

    async def health_check(self) -> bool:
        return False


def create_llm(provider: str, **kwargs) -> BaseLLM:
    """工厂函数：根据 provider 创建 LLM 实例"""
    match provider:
        case "iflytek":
            return IFlytekSpark(**kwargs)
        case "tencent":
            return TencentHunyuan(**kwargs)
        case "local":
            return LocalLLM(**kwargs)
        case _:
            raise ValueError(f"未知的 LLM provider: {provider}")
