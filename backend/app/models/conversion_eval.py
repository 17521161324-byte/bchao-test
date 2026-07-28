"""ASR 文本转化评估模型。

业务基础维度为检查记录 exam_record_id（当前数据库中对应 patient_records.id）。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class AsrConversionBatch(Base):
    """ASR 转化评估批次。一个批次下有多条 AsrConversionRecord。"""
    __tablename__ = "asr_conversion_batches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    date_scope = Column(String(50), default="")
    selected_dates = Column(JSON, default=list)
    asr_source_type = Column(String(30), default="latest_success", index=True)  # latest_success / config_hash
    asr_config_hash = Column(String(64), nullable=True, index=True)
    conversion_version = Column(String(50), default="manual")
    record_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    reviewed_count = Column(Integer, default=0)
    average_accuracy = Column(Float, default=0.0)
    status = Column(String(30), default="draft", index=True)  # draft / active / completed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    records = relationship("AsrConversionRecord", back_populates="batch")


class AsrConversionRecord(Base):
    """一次 ASR 文本转化评估记录。"""
    __tablename__ = "asr_conversion_records"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("asr_conversion_batches.id"), nullable=True, index=True)
    exam_record_id = Column(Integer, ForeignKey("patient_records.id"), nullable=False, index=True)
    asr_result_id = Column(Integer, ForeignKey("patient_asr_results.id"), nullable=True, index=True)
    reference_asr_id = Column(Integer, ForeignKey("asr_reference_transcripts.id"), nullable=True, index=True)

    record_id_snapshot = Column(String(50), index=True)
    date_snapshot = Column(String(8), index=True)
    asr_model_name = Column(String(100), nullable=True)
    source_config_hash = Column(String(64), nullable=True, index=True)

    raw_text = Column(Text, default="")
    converted_text = Column(Text, default="")
    reference_text = Column(Text, default="")
    conversion_version = Column(String(50), default="manual", index=True)
    status = Column(String(30), default="ready", index=True)  # ready / failed
    error_message = Column(Text, nullable=True)
    review_status = Column(String(30), default="pending", index=True)
    llm_eval_status = Column(String(30), default="not_started", index=True)

    metrics_summary = Column(JSON, default=dict)

    # 风险检查相关字段
    warnings = Column(Text, nullable=True)  # 风险警告文本
    risk_passed = Column(Integer, default=1)  # 风险检查是否通过 (0/1)
    risk_blocked = Column(Integer, default=0)  # 是否被阻断 (0/1)
    fields_snapshot = Column(JSON, nullable=True)  # 解析出的字段快照

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    exam_record = relationship("PatientRecord")
    asr_result = relationship("PatientAsrResult")
    reference_asr = relationship("AsrReferenceTranscript")
    batch = relationship("AsrConversionBatch", back_populates="records")
    details = relationship("AsrConversionDetail", back_populates="record", cascade="all, delete-orphan")
    reviews = relationship("AsrConversionReview", back_populates="record", cascade="all, delete-orphan")


class AsrConversionDetail(Base):
    """单个转化片段。"""
    __tablename__ = "asr_conversion_details"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("asr_conversion_records.id"), nullable=False, index=True)

    raw_fragment = Column(Text, default="")
    converted_fragment = Column(Text, default="")
    raw_start = Column(Integer, nullable=True)
    raw_end = Column(Integer, nullable=True)
    context_before = Column(Text, default="")
    context_after = Column(Text, default="")

    action_type = Column(String(30), default="replace", index=True)
    category = Column(String(50), default="other", index=True)
    rule_id = Column(String(80), nullable=True, index=True)
    rule_version = Column(String(50), nullable=True, index=True)
    confidence = Column(Float, nullable=True)

    risk_level = Column(String(30), default="low", index=True)
    risk_type = Column(String(50), nullable=True, index=True)
    system_judgement = Column(String(30), default="pending", index=True)
    manual_judgement = Column(String(30), nullable=True, index=True)
    final_judgement = Column(String(30), default="pending", index=True)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    record = relationship("AsrConversionRecord", back_populates="details")
    reviews = relationship("AsrConversionReview", back_populates="detail", cascade="all, delete-orphan")


class AsrConversionReview(Base):
    """人工审校记录。"""
    __tablename__ = "asr_conversion_reviews"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("asr_conversion_records.id"), nullable=False, index=True)
    detail_id = Column(Integer, ForeignKey("asr_conversion_details.id"), nullable=True, index=True)
    review_action = Column(String(30), nullable=False, index=True)
    is_high_risk = Column(Integer, default=0)
    high_risk_type = Column(String(50), nullable=True, index=True)
    note = Column(Text, nullable=True)
    reviewer = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    record = relationship("AsrConversionRecord", back_populates="reviews")
    detail = relationship("AsrConversionDetail", back_populates="reviews")


class AsrConversionMetric(Base):
    """转化评估指标快照。"""
    __tablename__ = "asr_conversion_metrics"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("asr_conversion_records.id"), nullable=False, index=True)
    category = Column(String(50), default="overall", index=True)
    rule_version = Column(String(50), nullable=True, index=True)
    metric_type = Column(String(50), nullable=False, index=True)
    numerator = Column(Integer, default=0)
    denominator = Column(Integer, default=0)
    value = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    record = relationship("AsrConversionRecord")
