export interface ExperimentBatch {
  id: number
  name: string
  description: string
  remark?: string
  selected_dates: string[]
  selected_patient_ids: string[]
  status: string
  total_tasks: number
  success_count: number
  failure_count: number
  patient_count?: number
  combination_count?: number
  created_at: string | Date
  updated_at: string | Date
  started_at?: string | Date | null
  completed_at?: string | Date | null
  metrics?: ExperimentMetrics
  combinations?: ExperimentCombination[]
  asr_models?: string[]
  llm_models?: string[]
  prompt_templates?: string[]
  asr_reuse_count?: number
  asr_generated_count?: number
  asr_failed_count?: number
  asr_reuse_rate?: number
}

export interface ExperimentCombination {
  id: number
  batch_id: number
  asr_model_id: number
  llm_model_id: number | null
  prompt_name: string
  prompt_template: string
  hotwords: string[]
  enabled: boolean
  created_at: string | Date
  asr_model_name?: string
  llm_model_name?: string
}

export interface ExperimentTaskSummary {
  id: number
  batch_id: number
  combination_id: number
  patient_id: number
  record_id?: string
  date?: string
  exam_record_id?: number
  stage: string
  status: string
  retry_count: number
  accuracy: number | null
  total_duration: number
  error_type: string | null
  error_message?: string | null
  created_at: string | Date

  // 快照字段
  asr_result_id?: number | null
  llm_result_id?: number | null
  asr_source?: string | null
  asr_model_name?: string | null
  llm_model_name?: string | null
  prompt_template_name?: string | null
  full_transcript?: string
  asr_results?: any[]
  llm_raw_output?: string | null
  structured_result?: any
  summary_text?: string | null
  evaluation?: any
  ground_truth?: any

  // 组合信息
  combination_asr_name?: string
  combination_llm_name?: string
  combination_prompt_name?: string
}

export interface ExperimentMetrics {
  total_tasks: number
  success_count: number
  failure_count: number
  patient_count?: number
  asr_success_rate: number
  asr_empty_rate: number
  avg_asr_duration: number
  field_accuracy: {
    endometrium_thickness: number
    endometrium_type: number
    ovary_size: number
    follicle: number
    remark: number
  }
  complete_patient_rate: number
  llm_failure_rate: number
  total_cost: number
}
