/**
 * TypeScript 类型定义
 */
export interface AudioSeg {
  id: number
  seg_index: number
  filename: string
  duration: number
  file_path: string
  file_size: number
}

export interface PatientRecord {
  id: number
  record_id: string
  date_folder_id: number
  timestamp_folder: string
  segs: AudioSeg[]
  has_result: boolean
}

export interface DateFolder {
  id: number
  date: string
  patient_count: number
  patients: PatientRecord[]
}

export interface DataStatus {
  total_dates: number
  total_patients: number
  matched_count: number
  audio_only_count: number
  result_only_count: number
}

export interface Follicle {
  size: number
  count: number
}

export interface BUltraResult {
  id: number
  record_id: string
  date: string
  source_file: string
  right_follicles: Follicle[]
  left_follicles: Follicle[]
  right_follicle_total: number
  left_follicle_total: number
  endometrium_thickness: number | null
  endometrium_type: string | null
  right_ovary_length: number | null
  right_ovary_width: number | null
  left_ovary_length: number | null
  left_ovary_width: number | null
  remark: string | null
}

export interface ModelConfig {
  id: number
  name: string
  model_type: 'asr' | 'llm'
  provider: string
  endpoint: string
  api_key?: string
  model_name?: string
  params: Record<string, any>
  is_default: boolean
  status: string
  created_at: string
  updated_at: string
}

export interface ASRSegResult {
  seg_index: number
  text: string
  duration: number
}

export interface TestRun {
  id: number
  record_id: string
  date: string
  asr_model_id: number
  llm_model_id: number | null
  prompt_version: string
  asr_results: ASRSegResult[]
  full_transcript: string
  llm_raw_output: string | null
  structured_result: Record<string, any> | null
  summary_text: string | null
  evaluation: Record<string, any> | null
  accuracy: number | null
  human_corrected: boolean
  duration_seconds: number
  created_at: string
}

export interface TestProgressEvent {
  stage: 'asr' | 'llm' | 'complete' | 'error'
  current?: number
  total?: number
  seg_text?: string
  message?: string
}

export interface Batch {
  id: number
  date: string
  patient_count: number
  matched_count: number
}

export interface DataIssue {
  type: 'no_audio_has_result' | 'missing_files' | 'duplicate'
  date: string
  record_id: string
  patient_id: number
  detail: string
  action: string
  missing_files?: string[]
}

export interface VerificationResult {
  total_issues: number
  issues: DataIssue[]
}

export interface PatientExamination {
  id: number
  record_id: string
  date: string
  date_folder_id: number
  timestamp_folder: string
  segs: AudioSeg[]
  result: BUltraResult | null
}

export interface PatientGroup {
  record_id: string
  examinations: PatientExamination[]
}
