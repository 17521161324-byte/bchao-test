"""
实验批量编排 ORM 模型
"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, JSON,
    UniqueConstraint, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.database import Base


class BatchStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    PARTIAL = "partial"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStage(str, enum.Enum):
    ASR = "asr"
    LLM = "llm"


class ExperimentBatch(Base):
    """实验批次"""
    __tablename__ = "experiment_batches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    remark = Column(Text, default="")  # 实验备注（独立于描述）
    selected_dates = Column(JSON, default=list)  # ["20260622", "20260623"]
    selected_patient_ids = Column(JSON, default=list)  # ["A017750", "A017503"]
    status = Column(String(20), default=BatchStatus.PENDING.value)
    total_tasks = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    combinations = relationship("ExperimentCombination", back_populates="batch", cascade="all, delete-orphan")
    tasks = relationship("ExperimentTask", back_populates="batch", cascade="all, delete-orphan")


class ExperimentCombination(Base):
    """实验组合（ASR + LLM + 提示词 + 热词）"""
    __tablename__ = "experiment_combinations"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("experiment_batches.id"), nullable=False)
    asr_model_id = Column(Integer, ForeignKey("model_configs.id"), nullable=False)
    llm_model_id = Column(Integer, ForeignKey("model_configs.id"), nullable=True)
    prompt_name = Column(String(100), default="")
    prompt_template = Column(Text, default="")
    hotwords = Column(JSON, default=list)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    batch = relationship("ExperimentBatch", back_populates="combinations")
    asr_model = relationship("ModelConfig", foreign_keys=[asr_model_id])
    llm_model = relationship("ModelConfig", foreign_keys=[llm_model_id])
    tasks = relationship("ExperimentTask", back_populates="combination")


class ExperimentTask(Base):
    """实验任务（患者 × 组合）"""
    __tablename__ = "experiment_tasks"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("experiment_batches.id"), nullable=False)
    combination_id = Column(Integer, ForeignKey("experiment_combinations.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patient_records.id"), nullable=False)

    stage = Column(String(20), default=TaskStage.ASR.value)
    status = Column(String(20), default=TaskStatus.PENDING.value)
    retry_count = Column(Integer, default=0)

    # Lease fields for worker claiming
    worker_id = Column(String(100), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)

    # ASR results
    asr_results = Column(JSON, default=list)
    full_transcript = Column(Text, default="")
    asr_duration = Column(Float, default=0.0)

    # LLM results
    llm_raw_output = Column(Text, nullable=True)
    structured_result = Column(JSON, nullable=True)
    summary_text = Column(Text, nullable=True)
    llm_duration = Column(Float, default=0.0)

    # Evaluation
    evaluation = Column(JSON, nullable=True)
    accuracy = Column(Float, nullable=True)

    # Cost and error tracking
    total_duration = Column(Float, default=0.0)
    cost = Column(Float, default=0.0)
    error_type = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    # 患者级 ASR/LLM 结果引用
    asr_result_id = Column(Integer, ForeignKey("patient_asr_results.id"), nullable=True)
    llm_result_id = Column(Integer, ForeignKey("patient_llm_results.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Constraints
    __table_args__ = (
        UniqueConstraint("batch_id", "combination_id", "patient_id", name="uq_task_patient_combination"),
    )

    # Relationships
    batch = relationship("ExperimentBatch", back_populates="tasks")
    combination = relationship("ExperimentCombination", back_populates="tasks")
    patient = relationship("PatientRecord")
