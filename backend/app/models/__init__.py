"""
SQLAlchemy 数据模型
"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

from app.models.experiment import ExperimentBatch, ExperimentCombination, ExperimentTask
from app.models.patient_result import PatientAsrResult, PatientLlmResult


class DateFolder(Base):
    """日期文件夹"""
    __tablename__ = "date_folders"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String(8), unique=True, index=True)  # 20260622
    path = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)

    patients = relationship("PatientRecord", back_populates="date_folder")


class PatientRecord(Base):
    """患者病历号记录"""
    __tablename__ = "patient_records"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(String(50), index=True)  # 病历号 A017750
    date_folder_id = Column(Integer, ForeignKey("date_folders.id"))
    timestamp_folder = Column(String(50))  # 时间戳文件夹名
    created_at = Column(DateTime, default=datetime.utcnow)

    date_folder = relationship("DateFolder", back_populates="patients")
    segs = relationship("AudioSeg", back_populates="patient", cascade="all, delete-orphan")
    result = relationship("BUltraResult", back_populates="patient", uselist=False)


class AudioSeg(Base):
    """音频分段"""
    __tablename__ = "audio_segs"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patient_records.id"))
    seg_index = Column(Integer)  # seg-0001 → 1
    filename = Column(String(200))
    duration = Column(Float, default=0.0)  # 秒
    file_path = Column(String(500))
    file_size = Column(Integer, default=0)  # 字节
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("PatientRecord", back_populates="segs")


class BUltraResult(Base):
    """B 超真实结果（ground truth）"""
    __tablename__ = "b_ultra_results"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patient_records.id"), unique=True)
    record_id = Column(String(50), index=True)
    date = Column(String(8))
    source_file = Column(String(200))  # 来源 xlsx 文件名

    # 卵泡数据（JSON 结构化）
    right_follicles = Column(JSON)  # [{"size": 16.4, "count": 1}, ...]
    left_follicles = Column(JSON)
    right_follicle_total = Column(Integer, default=0)
    left_follicle_total = Column(Integer, default=0)

    # 内膜
    endometrium_thickness = Column(Float, nullable=True)
    endometrium_type = Column(String(20), nullable=True)

    # 卵巢
    right_ovary_length = Column(Float, nullable=True)
    right_ovary_width = Column(Float, nullable=True)
    left_ovary_length = Column(Float, nullable=True)
    left_ovary_width = Column(Float, nullable=True)

    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("PatientRecord", back_populates="result")


class ModelConfig(Base):
    """模型配置"""
    __tablename__ = "model_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))  # 本地 FunASR
    model_type = Column(String(20))  # asr / llm
    provider = Column(String(50))  # local / iflytek / tencent
    endpoint = Column(String(500))
    api_key = Column(String(500), nullable=True)
    api_secret = Column(String(500), nullable=True)
    secret_key = Column(String(500), nullable=True)  # 火山引擎签名密钥
    model_name = Column(String(100), nullable=True)
    params = Column(JSON, default=dict)  # 额外参数
    is_default = Column(Boolean, default=False)
    status = Column(String(20), default="active")  # active / inactive
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TestRun(Base):
    """测试记录"""
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(String(50), index=True)
    date = Column(String(8))
    asr_model_id = Column(Integer, ForeignKey("model_configs.id"))
    llm_model_id = Column(Integer, ForeignKey("model_configs.id"), nullable=True)
    prompt_version = Column(String(50), default="v1.0")

    # ASR 结果
    asr_results = Column(JSON)  # [{"seg_index": 1, "text": "...", "duration": 1.2}, ...]
    full_transcript = Column(Text)

    # LLM 结果
    llm_raw_output = Column(Text, nullable=True)
    structured_result = Column(JSON, nullable=True)
    summary_text = Column(Text, nullable=True)

    # 评估
    evaluation = Column(JSON, nullable=True)  # 各字段对比结果
    accuracy = Column(Float, nullable=True)
    human_corrected = Column(Boolean, default=False)

    # 元信息
    duration_seconds = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class PromptTemplate(Base):
    """LLM 提示词模版"""
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)  # 模版名称
    content = Column(Text)  # 模版内容（含 {transcript} 占位符）
    is_default = Column(Boolean, default=False)  # 是否为默认模版
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
