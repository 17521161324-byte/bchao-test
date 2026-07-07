"""
配置管理
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import json
import os


# B 超领域默认热词 (当接口和模型配置均未提供时使用)
DEFAULT_ASR_HOTWORDS: list[str] = [
    "卵泡", "优势卵泡", "窦卵泡",
    "左卵巢", "右卵巢", "左侧卵巢", "右侧卵巢",
    "子宫内膜", "内膜", "内膜厚度", "内膜回声",
    "A型", "B型", "C型",
    "盆腔积液", "宫腔", "子宫",
    "黄体", "囊肿", "肌瘤",
    "回声", "无回声", "低回声", "强回声",
    "毫米", "厘米", "乘", "大小",
    "未见明显异常",
]


def resolve_hotwords(
    hotwords: list[str] | None,
    model_params: dict | None = None,
) -> list[str] | None:
    """按优先级解析热词

    优先级:
    1. 接口传入 hotwords
    2. 模型配置 params.hotwords
    3. DEFAULT_ASR_HOTWORDS
    全空返回 None
    """
    # 1. 接口传入
    if hotwords:
        cleaned = [w.strip() for w in hotwords if w and w.strip()]
        if cleaned:
            return cleaned

    # 2. 模型配置
    if model_params:
        model_hotwords = model_params.get("hotwords")
        if model_hotwords and isinstance(model_hotwords, list):
            cleaned = [w.strip() for w in model_hotwords if w and w.strip()]
            if cleaned:
                return cleaned

    # 3. 默认
    if DEFAULT_ASR_HOTWORDS:
        return list(DEFAULT_ASR_HOTWORDS)

    return None


class Settings(BaseSettings):
    APP_NAME: str = "bchao-test"
    APP_ENV: str = "development"

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 数据库
    DATABASE_URL: str = "sqlite:///./data/bchao.db"

    # 文件存储
    DATA_DIR: str = "./data"
    UPLOAD_DIR: str = "./uploads"
    RECORDINGS_DIR: str = "./data/recordings"

    # 本地 ASR
    LOCAL_ASR_URL: str = "http://172.16.10.142:50000"

    # 默认模型
    DEFAULT_ASR_PROVIDER: str = "local"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost:5190", "http://localhost:5191", "http://localhost:5192", "http://localhost:5180"]

    # 日志
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 确保目录存在
        for d in [self.DATA_DIR, self.UPLOAD_DIR, self.RECORDINGS_DIR]:
            os.makedirs(d, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
