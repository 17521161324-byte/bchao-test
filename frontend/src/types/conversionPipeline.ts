/**
 * 医疗 ASR 结构化处理流水线类型定义
 * 与后端 backend/app/schemas/conversion_pipeline.py 的 Schema 字段对应
 * （run-to-step / PATCH 步骤输出 / continue / GET executions 为文档新增契约，
 *   后端尚未实现时前端按契约对接，字段均做可选容错）
 */

export type PipelineResultLevel =
  | 'AUTO_ACCEPT'
  | 'REVIEW_REQUIRED'
  | 'MANUAL_AUDIO_REVIEW'

export type PipelineStepStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'warning'
  | 'failed'
  | 'manual_edited'
  | 'dirty'

/** 步骤人工修改信息（实施说明 §8.2 建议数据结构，后端可选返回） */
export interface StepManualEditInfo {
  system_output_text?: string | null
  manual_output_text?: string | null
  effective_output_text?: string | null
  edited?: boolean
  edited_by?: string | null
  edited_at?: string | null
  edit_note?: string | null
}

export interface PipelineStep extends StepManualEditInfo {
  id?: number
  step_code: string
  step_name: string
  step_order: number
  status: PipelineStepStatus
  input_text: string
  output_text: string
  conversions: Record<string, any>[]
  rule_hits: Record<string, any>[]
  warnings: string[]
  state_before: Record<string, any>
  state_after: Record<string, any>
  fields: Record<string, any>
  source_spans: Record<string, any>[]
  duration_ms: number
  config_hash: string
  error_message?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface PipelineExecution {
  id: number
  source_type: string
  source_id?: number | null
  input_source: string
  input_text: string
  scene: string
  model_name: string
  rule_version_id?: number | null
  rule_version_code: string
  config_hash: string
  status: string
  result_level?: PipelineResultLevel | null
  final_text: string
  final_fields: Record<string, any>
  final_warnings: string[]
  final_risk_items: Record<string, any>[]
  source_patient_id?: number | null
  source_record_id?: string | null
  source_date?: string | null
  source_config_hash?: string | null
  source_asr_model_name?: string | null
  reference_text?: string | null
  reference_base_asr_result_id?: number | null
  reference_base_config_hash?: string | null
  reference_match_type?: 'exact_base' | 'config_match' | 'same_exam' | null
  truth_fields?: Record<string, any>
  steps: PipelineStep[]
  /** fork 产生的执行会带来源执行 id（后端可选字段） */
  parent_execution_id?: number | null
  created_at?: string | null
  updated_at?: string | null
  /** 是否包含人工修改的步骤（后端可选字段） */
  manual_edited?: boolean
}

/** 创建执行请求参数（POST /conversion-pipeline/executions） */
export interface PipelineExecutionCreate {
  source_type?: 'manual' | 'text_validation_run' | 'patient_asr_result'
  source_id?: number
  input_source?: 'manual' | 'raw_asr_text' | 'corrected_text'
  text?: string
  scene?: string
  model_name?: string
  rule_version_id?: number
  run_mode?: 'create_only' | 'run_all'
}

/** GET /conversion-pipeline/executions 列表项（最近调试 / 执行历史） */
export interface PipelineExecutionSummary {
  id: number
  source_type: string
  source_id?: number | null
  input_source: string
  input_text: string
  scene: string
  rule_version_id?: number | null
  rule_version_code: string
  config_hash: string
  status: string
  result_level?: PipelineResultLevel | null
  final_text: string
  final_fields: Record<string, any>
  final_warnings: string[]
  final_risk_items: Record<string, any>[]
  manual_edited?: boolean
  created_at?: string | null
  /** 人工修改标记（旧后端可能返回 edited） */
  edited?: boolean
}

/** GET /conversion-pipeline/executions 查询参数（实施说明 §11.5） */
export interface PipelineExecutionListParams {
  source_type?: string
  source_id?: number
  rule_version_id?: number
  limit?: number
}

/** POST /conversion-pipeline/executions/{id}/run-to-step 请求（实施说明 §11.2） */
export interface PipelineRunToStepRequest {
  step_code: string
}

/** PATCH /conversion-pipeline/executions/{id}/steps/{step_code}/output 请求（实施说明 §11.3） */
export interface PipelineStepOutputPatch {
  manual_output_text: string
  edit_note?: string
}

/** PATCH 步骤输出响应：被标记为 dirty 的下游步骤（实施说明 §11.3） */
export interface PipelineStepOutputPatchResult {
  step: PipelineStep
  invalidated_step_codes: string[]
}

/** POST /conversion-pipeline/executions/{id}/continue 请求（实施说明 §11.4） */
export interface PipelineContinueRequest {
  from_step_code: string
  run_mode?: 'run_all' | 'create_only'
}

/** 新旧执行对比结果（GET /conversion-pipeline/compare） */
export interface PipelineCompareResult {
  left_execution_id: number
  right_execution_id: number
  text_changed: boolean
  field_changes: Array<{
    field_code: string
    left_value: any
    right_value: any
  }>
  new_rule_hits: string[]
  removed_rule_hits: string[]
  new_warnings: string[]
  removed_warnings: string[]
}
