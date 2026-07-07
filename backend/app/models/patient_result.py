"""
患者级 ASR/LLM 持久化结果模型

patient_asr_results / patient_llm_results 是患者级正式结果;
experiment_tasks 保留自己快照字段,同时通过 asr_result_id / llm_result_id 引用患者结果。
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey, JSON, Text, DateTime
)
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class PatientAsrResult(Base):
    """患者级 ASR 持久化结果"""
    __tablename__ = "patient_asr_results"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patient_records.id"), nullable=False, index=True)
    record_id = Column(String(50), index=True)       # 冗余快照
    date = Column(String(8))                          # 冗余快照
    asr_model_id = Column(Integer, ForeignKey("model_configs.id"))
    asr_model_name = Column(String(100))              # 冗余快照
    provider = Column(String(50))
    hotwords = Column(JSON, default=list)
    segments = Column(JSON, default=list)             # [{seg_index, text, duration}]
    full_transcript = Column(Text, default="")
    duration_seconds = Column(Float, default=0.0)
    status = Column(String(20), default="running")    # running/success/failed
    error_message = Column(Text, nullable=True)
    is_current = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("PatientRecord")


class PatientLlmResult(Base):
    """患者级 LLM 持久化结果"""
    __tablename__ = "patient_llm_results"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patient_records.id"), nullable=False, index=True)
    asr_result_id = Column(Integer, ForeignKey("patient_asr_results.id"), nullable=True)
    llm_model_id = Column(Integer, ForeignKey("model_configs.id"))
    llm_model_name = Column(String(100))              # 冗余快照
    prompt_version = Column(String(50), default="v1.0")
    prompt_content = Column(Text, default="")          # 冗余快照
    structured_result = Column(JSON, nullable=True)
    summary_text = Column(Text, nullable=True)
    raw_output = Column(Text, nullable=True)
    evaluation = Column(JSON, nullable=True)
    accuracy = Column(Float, nullable=True)
    status = Column(String(20), default="running")     # running/success/failed
    error_message = Column(Text, nullable=True)
    is_current = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("PatientRecord")
    asr_result = relationship("PatientAsrResult")
