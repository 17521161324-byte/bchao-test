"""
Pydantic 请求/响应模型
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from app.schemas.experiment import (
    ExperimentBatchCreate, ExperimentBatchOut,
    ExperimentCombinationCreate, ExperimentCombinationUpdate, ExperimentCombinationOut,
    ExperimentTaskSummary, ExperimentMetrics,
    ExperimentDetailOut, ExperimentListResponse,
)


# ========== 录音相关 ==========

class AudioSegOut(BaseModel):
    id: int
    seg_index: int
    filename: str
    duration: float
    file_path: str
    file_size: int

    class Config:
        from_attributes = True


class PatientRecordOut(BaseModel):
    id: int
    record_id: str
    date_folder_id: int
    timestamp_folder: str
    segs: list[AudioSegOut] = []
    has_result: bool = False

    class Config:
        from_attributes = True


class DateFolderOut(BaseModel):
    id: int
    date: str
    patient_count: int = 0
    patients: list[PatientRecordOut] = []

    class Config:
        from_attributes = True


class DataStatusOut(BaseModel):
    total_dates: int
    total_patients: int
    matched_count: int
    audio_only_count: int
    result_only_count: int


# ========== 结果相关 ==========

class BUltraResultOut(BaseModel):
    id: int
    record_id: str
    date: str
    source_file: str
    right_follicles: list[dict] = []
    left_follicles: list[dict] = []
    right_follicle_total: int = 0
    left_follicle_total: int = 0
    endometrium_thickness: Optional[float] = None
    endometrium_type: Optional[str] = None
    right_ovary_length: Optional[float] = None
    right_ovary_width: Optional[float] = None
    left_ovary_length: Optional[float] = None
    left_ovary_width: Optional[float] = None
    remark: Optional[str] = None

    class Config:
        from_attributes = True


# ========== 模型配置相关 ==========

class ModelConfigCreate(BaseModel):
    name: str
    model_type: str  # asr / llm
    provider: str  # local / iflytek / tencent
    endpoint: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    model_name: Optional[str] = None
    params: dict = Field(default_factory=dict)
    is_default: bool = False


class ModelConfigUpdate(BaseModel):
    name: Optional[str] = None
    model_type: Optional[str] = None
    provider: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    model_name: Optional[str] = None
    params: Optional[dict] = None
    is_default: Optional[bool] = None
    status: Optional[str] = None


class ModelConfigOut(BaseModel):
    id: int
    name: str
    model_type: str
    provider: str
    endpoint: str
    model_name: Optional[str] = None
    params: dict
    is_default: bool
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ModelTestResult(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[float] = None


# ========== 测试相关 ==========

class TestStartRequest(BaseModel):
    record_id: str
    asr_model_id: int
    llm_model_id: Optional[int] = None
    prompt_version: str = "v1.0"


class ASRSegResult(BaseModel):
    seg_index: int
    text: str
    duration: float = 0.0


class TestResultOut(BaseModel):
    id: int
    record_id: str
    date: str
    asr_model_id: int
    llm_model_id: Optional[int]
    prompt_version: str
    asr_results: list[ASRSegResult] = []
    full_transcript: str = ""
    llm_raw_output: Optional[str] = None
    structured_result: Optional[dict] = None
    summary_text: Optional[str] = None
    evaluation: Optional[dict] = None
    accuracy: Optional[float] = None
    human_corrected: bool = False
    duration_seconds: float = 0.0
    created_at: datetime

    class Config:
        from_attributes = True


class TestProgressEvent(BaseModel):
    stage: str  # asr / llm / complete / error
    current: Optional[int] = None
    total: Optional[int] = None
    seg_text: Optional[str] = None
    message: Optional[str] = None


class EvaluationUpdate(BaseModel):
    structured_result: dict
    human_corrected: bool = True
    correction_note: Optional[str] = None


# ========== 通用 ==========

class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Optional[dict] = None
