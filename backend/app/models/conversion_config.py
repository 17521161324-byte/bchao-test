"""ASR conversion lexicon/rule configuration models."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ConversionConfigVersion(Base):
    __tablename__ = "conversion_config_versions"

    id = Column(Integer, primary_key=True, index=True)
    version_code = Column(String(80), nullable=False, unique=True, index=True)
    version_name = Column(String(200), nullable=False)
    status = Column(String(30), default="draft", index=True)  # draft/testing/published/rolled_back
    description = Column(Text, default="")
    parent_version_id = Column(Integer, ForeignKey("conversion_config_versions.id"), nullable=True)
    # P0-10：发布回归门槛
    latest_regression_status = Column(String(30), default="", index=True)  # pending/passed/failed
    latest_regression_config_hash = Column(String(64), default="")
    review_status = Column(String(30), default="")  # pending/reviewed
    created_by = Column(String(80), default="")
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lexicon_entries = relationship("ConversionLexiconEntry", back_populates="version", cascade="all, delete-orphan")
    rule_entries = relationship("ConversionRuleEntry", back_populates="version", cascade="all, delete-orphan")


class ConversionLexiconEntry(Base):
    __tablename__ = "conversion_lexicon_entries"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("conversion_config_versions.id"), nullable=False, index=True)
    rule_code = Column(String(80), nullable=False, index=True)
    error_text = Column(Text, nullable=False)
    standard_text = Column(Text, nullable=False)
    asr_model = Column(String(120), default="")
    business_scene = Column(String(120), default="通用")
    required_context = Column(Text, default="")
    excluded_context = Column(Text, default="")
    match_type = Column(String(30), default="exact")
    action = Column(String(30), default="AUTO")
    risk_level = Column(String(30), default="medium")
    confidence = Column(Float, default=0.95)
    priority = Column(Integer, default=100)
    enabled = Column(Integer, default=1)
    notes = Column(Text, default="")
    hit_count = Column(Integer, default=0)
    accuracy = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    version = relationship("ConversionConfigVersion", back_populates="lexicon_entries")


class ConversionRuleEntry(Base):
    __tablename__ = "conversion_rule_entries"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("conversion_config_versions.id"), nullable=False, index=True)
    rule_code = Column(String(80), nullable=False, index=True)
    rule_type = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    pattern = Column(Text, default="")
    replacement = Column(Text, default="")
    condition_config = Column(JSON, default=dict)
    example_input = Column(Text, default="")
    example_output = Column(Text, default="")
    action = Column(String(30), default="AUTO")
    risk_level = Column(String(30), default="medium")
    priority = Column(Integer, default=100)
    enabled = Column(Integer, default=1)
    editable = Column(Integer, default=0)
    system_handler = Column(String(120), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    version = relationship("ConversionConfigVersion", back_populates="rule_entries")
