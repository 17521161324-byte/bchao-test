"""ASR text correction and rule extraction validation models."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class TextValidationRun(Base):
    """One validation run for ASR text -> corrected text -> rule extraction."""
    __tablename__ = "text_validation_runs"

    id = Column(Integer, primary_key=True, index=True)
    exam_record_id = Column(Integer, ForeignKey("patient_records.id"), nullable=False, index=True)
    asr_result_id = Column(Integer, ForeignKey("patient_asr_results.id"), nullable=False, index=True)
    llm_model_id = Column(Integer, ForeignKey("model_configs.id"), nullable=True, index=True)
    prompt_template_id = Column(Integer, ForeignKey("prompt_templates.id"), nullable=True, index=True)
    correction_template_id = Column(Integer, ForeignKey("text_correction_templates.id"), nullable=True, index=True)
    rule_version_id = Column(Integer, ForeignKey("conversion_config_versions.id"), nullable=True, index=True)

    record_id_snapshot = Column(String(50), index=True)
    date_snapshot = Column(String(8), index=True)
    asr_model_name = Column(String(100), nullable=True)
    asr_config_hash = Column(String(64), nullable=True, index=True)
    llm_model_name = Column(String(100), nullable=True)
    prompt_template_name = Column(String(100), nullable=True)
    rule_version = Column(String(80), default="manual", index=True)

    raw_asr_text = Column(Text, default="")
    corrected_text = Column(Text, default="")
    llm_raw_output = Column(Text, nullable=True)
    structured_result = Column(JSON, default=dict)
    source_spans = Column(JSON, default=list)
    conversions = Column(JSON, default=list)  # 命中规则转化记录
    segments = Column(JSON, default=list)  # 业务片段（医学名词/定位词/数据/噪声）
    warnings = Column(JSON, default=list)  # 规则解析/风险警示文本
    risk_items = Column(JSON, default=list)  # 结构化警示项（rule_id/action/severity/message）
    evaluation = Column(JSON, default=dict)
    accuracy = Column(Float, nullable=True)
    status = Column(String(30), default="success", index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    exam_record = relationship("PatientRecord")
    asr_result = relationship("PatientAsrResult")
    llm_model = relationship("ModelConfig", foreign_keys=[llm_model_id])
    prompt_template = relationship("PromptTemplate")
    correction_template = relationship("TextCorrectionTemplate")
    rule_config_version = relationship("ConversionConfigVersion")


class TextCorrectionTemplate(Base):
    """Prompt template dedicated to full-text ASR correction."""
    __tablename__ = "text_correction_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True, index=True)
    content = Column(Text, nullable=False)
    is_default = Column(Integer, default=0, index=True)
    status = Column(String(30), default="active", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
