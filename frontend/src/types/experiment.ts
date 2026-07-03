export interface ExperimentBatch {
  id: number
  name: string
  description: string
  selected_dates: string[]
  selected_patient_ids: string[]
  status: string
  total_tasks: number
  success_count: number
  failure_count: number
  created_at: string
  updated_at: string
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
  created_at: string
}

export interface ExperimentTaskSummary {
  id: number
  batch_id: number
  combination_id: number
  patient_id: number
  stage: string
  status: string
  retry_count: number
  accuracy: number | null
  total_duration: float
  error_type: string | null
  created_at: string
}

export interface ExperimentMetrics {
  total_tasks: number
  success_count: number
  failure_count: number
  asr_success_rate: number
  asr_empty_rate: number
  avg_asr_duration: number
  follicle_accuracy: number
  endometrium_accuracy: number
  ovary_accuracy: number
  complete_patient_rate: number
  llm_failure_rate: number
  total_cost: number
}
