"""
LLM 抽象层与实现
"""
import httpx
import json
import re
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


class OpenAILLM(BaseLLM):
    """OpenAI 兼容协议的 LLM 客户端，适用于 DeepSeek / MiMo / OpenAI 等"""

    def __init__(self, api_key: str, endpoint: str, model_name: str = "", **kwargs):
        self.api_key = api_key
        # 规范化 endpoint：去掉末尾 /chat/completions（如已拼接）和尾部斜杠
        endpoint = endpoint.rstrip("/")
        if endpoint.endswith("/chat/completions"):
            endpoint = endpoint[: -len("/chat/completions")]
        self.endpoint = endpoint
        self.model_name = model_name or kwargs.get("model_name", "")
        # DeepSeek 倾向于用大写 Authorization
        self._use_bearer = kwargs.get("auth_scheme", "bearer").lower() == "bearer"

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._use_bearer:
            # 只有 api_key 非空时才加 Authorization, 否则 httpx 会报 "Illegal header value b'Bearer '"
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            if self.api_key:
                headers["api-key"] = self.api_key
        return headers

    async def _chat_complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        url = f"{self.endpoint}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _extract_json(self, text: str) -> dict | None:
        """从 LLM 回复中提取 JSON 块"""
        # 优先匹配 ```json ... ``` 或 ``` ... ```
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        # 匹配首个 { ... }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"JSON 解析失败: {text[:200]}")
            return None

    async def extract(self, transcript: str, prompt_template: str) -> LLMResponse:
        # 用字符串替换而非 .format()，避免 JSON 示例花括号被误解析为占位符
        user_prompt = prompt_template.replace("{transcript}", transcript)
        # 兜底：若模板没有 {transcript} 占位符，直接拼接
        if "{transcript}" not in prompt_template:
            user_prompt = f"{prompt_template}\n\n## 转写文本\n\n{transcript}"
        raw = await self._chat_complete(
            system_prompt="你是一名医学数据结构化专家。请严格按照用户要求的 JSON 格式返回，不要附加任何解释或 Markdown。",
            user_prompt=user_prompt,
        )
        structured = self._extract_json(raw)
        return LLMResponse(raw_text=raw, structured=structured)

    async def health_check(self) -> bool:
        try:
            url = f"{self.endpoint}/chat/completions"
            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5,
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, headers=self._headers(), json=payload)
                return resp.status_code == 200
        except Exception:
            return False


# 预留接口（占位）
class IFlytekSpark(BaseLLM):
    """讯飞星火 LLM（预留接口）"""
    def __init__(self, api_key: str, model_name: str = "spark-v3.5", **kwargs):
        self.api_key = api_key
        self.model_name = model_name
    async def extract(self, transcript: str, prompt_template: str) -> LLMResponse:
        raise NotImplementedError("讯飞星火 LLM 待实现")
    async def health_check(self) -> bool:
        return False


class TencentHunyuan(BaseLLM):
    """腾讯混元 LLM（预留接口）"""
    def __init__(self, api_key: str, model_name: str = "hunyuan-standard", **kwargs):
        self.api_key = api_key
        self.model_name = model_name
    async def extract(self, transcript: str, prompt_template: str) -> LLMResponse:
        raise NotImplementedError("腾讯混元 LLM 待实现")
    async def health_check(self) -> bool:
        return False


class LocalLLM(BaseLLM):
    """本地 LLM（预留接口）"""
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
        case "mimo" | "deepseek" | "openai":
            return OpenAILLM(**kwargs)
        case _:
            raise ValueError(f"未知的 LLM provider: {provider}")
