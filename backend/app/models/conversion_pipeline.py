"""流水线执行与步骤持久化模型（Task 13）。

新表由 Base.metadata.create_all 创建，不需要写 _ensure_column()。
"""
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class ConversionPipelineExecution(Base):
    __tablename__ = "conversion_pipeline_executions"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(50), default="manual", index=True)
    source_id = Column(Integer, nullable=True, index=True)
    input_source = Column(String(50), default="manual")
    input_text = Column(Text, nullable=False)
    scene = Column(String(120), default="")
    model_name = Column(String(120), default="")

    rule_version_id = Column(
        Integer,
        ForeignKey("conversion_config_versions.id"),
        nullable=True,
        index=True,
    )
    rule_version_code = Column(String(80), default="manual", index=True)
    config_snapshot = Column(JSON, default=dict)
    config_hash = Column(String(64), default="", index=True)

    status = Column(String(30), default="created", index=True)
    result_level = Column(String(40), nullable=True, index=True)
    final_text = Column(Text, default="")
    final_fields = Column(JSON, default=dict)
    final_warnings = Column(JSON, default=list)
    final_risk_items = Column(JSON, default=list)

    created_by = Column(String(80), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    steps = relationship(
        "ConversionPipelineStep",
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="ConversionPipelineStep.step_order",
    )


class ConversionPipelineStep(Base):
    __tablename__ = "conversion_pipeline_steps"
    __table_args__ = (
        UniqueConstraint(
            "execution_id",
            "step_code",
            name="uq_pipeline_execution_step",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(
        Integer,
        ForeignKey("conversion_pipeline_executions.id"),
        nullable=False,
        index=True,
    )
    step_code = Column(String(50), nullable=False, index=True)
    step_name = Column(String(100), nullable=False)
    step_order = Column(Integer, nullable=False)
    status = Column(String(30), default="pending", index=True)

    input_text = Column(Text, default="")
    output_text = Column(Text, default="")
    conversions = Column(JSON, default=list)
    rule_hits = Column(JSON, default=list)
    warnings = Column(JSON, default=list)
    state_before = Column(JSON, default=dict)
    state_after = Column(JSON, default=dict)
    fields = Column(JSON, default=dict)
    source_spans = Column(JSON, default=list)

    duration_ms = Column(Integer, default=0)
    config_hash = Column(String(64), default="", index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    execution = relationship(
        "ConversionPipelineExecution",
        back_populates="steps",
    )
