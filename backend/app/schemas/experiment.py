"""
实验批量编排 API Schema
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ExperimentBatchCreate(BaseModel):
    name: str
    description: str = ""
    selected_dates: list[str] = Field(default_factory=list)
    selected_patient_ids: list[str] = Field(default_factory=list)


class ExperimentPatientScopeUpdate(BaseModel):
    selected_patient_ids: list[str] = Field(default_factory=list)


class ExperimentControlAction(BaseModel):
    pass  # No body needed for start/pause/resume/cancel/retry


class ExperimentBatchOut(BaseModel):
    id: int
    name: str
    description: str
    selected_dates: list[str]
    status: str
    total_tasks: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExperimentCombinationCreate(BaseModel):
    asr_model_id: int
    llm_model_id: int | None = None
    prompt_name: str = ""
    prompt_template: str = ""
    hotwords: list[str] = Field(default_factory=list)


class ExperimentCombinationUpdate(BaseModel):
    asr_model_id: int | None = None
    llm_model_id: int | None = None
    prompt_name: str | None = None
    prompt_template: str | None = None
    hotwords: list[str] | None = None
    enabled: bool | None = None


class ExperimentCombinationOut(BaseModel):
    id: int
    batch_id: int
    asr_model_id: int
    llm_model_id: int | None
    prompt_name: str
    prompt_template: str
    hotwords: list[str]
    enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ExperimentTaskSummary(BaseModel):
    id: int
    batch_id: int
    combination_id: int
    patient_id: int
    stage: str
    status: str
    retry_count: int
    accuracy: float | None
    total_duration: float
    error_type: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ExperimentMetrics(BaseModel):
    combination_id: int
    total_tasks: int
    success_count: int
    failure_count: int
    asr_success_rate: float
    asr_empty_rate: float
    avg_asr_duration: float
    follicle_accuracy: float
    endometrium_accuracy: float
    ovary_accuracy: float
    complete_patient_rate: float
    llm_failure_rate: float
    total_cost: float


class ExperimentDetailOut(ExperimentBatchOut):
    combinations: list[ExperimentCombinationOut] = Field(default_factory=list)


class ExperimentListResponse(BaseModel):
    id: int
    name: str
    status: str
    total_tasks: int
    success_count: int
    failure_count: int
    created_at: datetime
