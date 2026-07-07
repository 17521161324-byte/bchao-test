"""
配置管理
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import json
import os


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
