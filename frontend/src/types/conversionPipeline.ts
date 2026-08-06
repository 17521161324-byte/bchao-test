/**
 * 医疗 ASR 结构化处理流水线类型定义
 * 与后端 backend/app/schemas/conversion_pipeline.py 的 Schema 字段对应
 */

export type PipelineResultLevel =
  | 'AUTO_ACCEPT'
  | 'REVIEW_REQUIRED'
  | 'MANUAL_AUDIO_REVIEW'

export type PipelineStepStatus = 'pending' | 'running' | 'success' | 'failed'

export interface PipelineStep {
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
  steps: PipelineStep[]
  /** fork 产生的执行会带来源执行 id（后端可选字段） */
  parent_execution_id?: number | null
}

/** 创建执行请求参数（POST /conversion-pipeline/executions） */
export interface PipelineExecutionCreate {
  source_type?: 'manual' | 'text_validation_run' | 'conversion_preview'
  source_id?: number
  input_source?: 'manual' | 'raw_asr_text' | 'corrected_text'
  text?: string
  scene?: string
  model_name?: string
  rule_version_id?: number
  run_mode?: 'create_only' | 'run_all'
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
