"""
检查记录级 ASR/LLM 持久化结果模型

业务语义:
- patient_id 实际为 exam_record_id (= patient_records.id)
- record_id (病历号) 可跨日期多次检查, 每次检查有独立 ID
- 结果必须关联到具体检查记录, 而非病历号
- experiment_tasks 保留快照字段, 通过 asr_result_id / llm_result_id 引用检查记录结果
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey, JSON, Text, DateTime
)
from sqlalchemy.ext.mutable import MutableList
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
    source = Column(String(50), default="normal", index=True)
    experiment_key = Column(String(100), nullable=True, index=True)
    config_hash = Column(String(64), nullable=True, index=True)
    config_snapshot = Column(JSON, nullable=True)
    hotwords = Column(MutableList.as_mutable(JSON), default=list)
    segments = Column(MutableList.as_mutable(JSON), default=list)             # [{seg_index, text, duration}]
    full_transcript = Column(Text, default="")
    duration_seconds = Column(Float, default=0.0)
    status = Column(String(20), default="running")    # running/success/failed
    error_message = Column(Text, nullable=True)
    is_current = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("PatientRecord")


class AsrReferenceTranscript(Base):
    """检查记录级标准 ASR 文本（人工校准稿）。

    用于 ASR 优化评估中的“标准答案”对比：
    - 不覆盖原始 ASR 历史结果；
    - 每个检查记录保留一条当前标准文本；
    - 可记录来源底稿 ASR，便于追溯从哪次识别结果修订而来。
    """
    __tablename__ = "asr_reference_transcripts"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patient_records.id"), nullable=False, unique=True, index=True)
    record_id = Column(String(50), index=True)
    date = Column(String(8), index=True)
    base_asr_result_id = Column(Integer, ForeignKey("patient_asr_results.id"), nullable=True)
    base_asr_model_name = Column(String(100), nullable=True)
    base_config_hash = Column(String(64), nullable=True, index=True)
    reference_text = Column(Text, nullable=False, default="")
    reference_annotations = Column(MutableList.as_mutable(JSON), default=list)
    note = Column(Text, nullable=True)
    is_current = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("PatientRecord")
    base_asr_result = relationship("PatientAsrResult")


class PatientLlmResult(Base):
    """患者级 LLM 持久化结果"""
    __tablename__ = "patient_llm_results"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patient_records.id"), nullable=False, index=True)
    asr_result_id = Column(Integer, ForeignKey("patient_asr_results.id"), nullable=True)
    llm_model_id = Column(Integer, ForeignKey("model_configs.id"))
    llm_model_name = Column(String(100))              # 冗余快照
    prompt_template_id = Column(Integer, ForeignKey("prompt_templates.id"), nullable=True)
    prompt_template_name = Column(String(100))        # 冗余快照
    prompt_version = Column(String(50), default="v1.0")
    prompt_content = Column(Text, default="")          # 冗余快照
    source = Column(String(50), default="normal", index=True)
    experiment_key = Column(String(100), nullable=True, index=True)
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


class AsrOptimizationPlan(Base):
    """ASR 优化评估配置方案（用户命名并持久化）"""
    __tablename__ = "asr_optimization_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    asr_model_id = Column(Integer, ForeignKey("model_configs.id"), nullable=False, index=True)
    params = Column(JSON, default=dict)
    config_hash = Column(String(64), nullable=False, unique=True, index=True)
    source = Column(String(30), default="custom", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    asr_model = relationship("ModelConfig")


class OptimizationFieldReviewMark(Base):
    """优化评估字段归因标记。

    与数据管理的全局字段标记不同，本表绑定到具体 LLM 历史结果。
    这样同一检查记录在不同 ASR 方案、LLM 模型、提示词版本下的归因不会互相污染。
    """
    __tablename__ = "optimization_field_review_marks"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patient_records.id"), nullable=False, index=True)
    field_group = Column(String(50), nullable=False, index=True)
    field_key = Column(String(50), nullable=True)
    asr_config_hash = Column(String(64), nullable=True, index=True)
    asr_result_id = Column(Integer, ForeignKey("patient_asr_results.id"), nullable=True, index=True)
    llm_result_id = Column(Integer, ForeignKey("patient_llm_results.id"), nullable=False, index=True)
    llm_model_id = Column(Integer, ForeignKey("model_configs.id"), nullable=True, index=True)
    prompt_template_id = Column(Integer, ForeignKey("prompt_templates.id"), nullable=True, index=True)
    prompt_template_name = Column(String(100), nullable=True)
    prompt_content_hash = Column(String(64), nullable=True, index=True)
    mark_type = Column(String(20), nullable=False)  # exclude / mismatch_note
    reason = Column(String(100), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("PatientRecord")
    asr_result = relationship("PatientAsrResult")
    llm_result = relationship("PatientLlmResult")
