/**
 * API 客户端封装
 */
import axios from 'axios'
import { message } from 'ant-design-vue'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

const client: any = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.response.use(
  (response: any) => response.data,
  (error: any) => {
    const config = error.config || {}
    const method = (config.method || 'GET').toUpperCase()
    const url = config.url || ''
    const status = error.response?.status
    const detail = error.response?.data?.detail
    const fallback = error.message || '请求失败'
    // 开发环境显示完整请求信息，便于定位（如 404 时区分"路由未注册"与"记录不存在"）
    const displayMessage = status
      ? `${method} ${url}：${status}${detail ? ` ${detail}` : ''}`
      : `${method} ${url}：${fallback}`
    message.error(displayMessage)
    console.error('[API ERROR]', { method, url, status, data: error.response?.data, requestData: config.data })
    return Promise.reject(error)
  }
)

// ========== 录音管理 ==========
export const audioApi = {
  getTree: () => client.get('/audio/tree'),
  getBatches: () => client.get('/audio/batches'),
  getPatients: (date?: string) => client.get('/audio/patients', { params: date ? { date } : {} }),
  getRecords: (date?: string) => client.get('/audio/records', { params: date ? { date } : {} }),
  getStatus: () => client.get('/audio/status'),
  verify: (date?: string) => client.get('/audio/verify', { params: date ? { date } : {} }),
  deletePatient: (patientId: number) => client.delete(`/audio/patient/${patientId}`),
  updatePatientNote: (patientId: number, note: string) => client.put(`/audio/patient/${patientId}/note`, { note }),
  exportLatestLlmResults: (patientIds: number[]) =>
    client.post('/audio/records/export-latest', { patient_ids: patientIds }, {
      responseType: 'blob',
      timeout: 300000,
    }),
  scan: () => client.post('/audio/scan'),
  getFileUrl: (path: string) => `${API_BASE}/audio/file?path=${encodeURIComponent(path)}`,
}

// ========== 结果管理 ==========
export const resultApi = {
  upload: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return client.post('/result/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },
  getByRecord: (recordId: string) => client.get(`/result/${recordId}`),
  update: (resultId: number, data: any) => client.put(`/result/${resultId}`, data),
  // 按检查记录 ID 读写真实 B 超结果
  getBUltraResult: (examRecordId: number) => client.get(`/result/exam/${examRecordId}/b-ultra`),
  updateBUltraResult: (examRecordId: number, data: any) => client.put(`/result/exam/${examRecordId}/b-ultra`, data),
}

// ========== 模型配置 ==========
export const modelApi = {
  list: (modelType?: string) => client.get('/model', { params: { model_type: modelType } }),
  create: (data: any) => client.post('/model', data),
  update: (id: number, data: any) => client.put(`/model/${id}`, data),
  delete: (id: number) => client.delete(`/model/${id}`),
  test: (id: number) => client.post(`/model/${id}/test`),
  initDefaults: () => client.post('/model/init-defaults'),
}

// ========== ASR 优化评估配置方案 ==========
export const asrOptimizationApi = {
  listPlans: () => client.get('/asr-optimization/plans'),
  savePlan: (data: {
    name: string
    asr_model_id: number
    params: any
    config_hash: string
    source?: string
  }) => client.post('/asr-optimization/plans', data),
  updatePlan: (id: number, data: any) => client.put(`/asr-optimization/plans/${id}`, data),
  deletePlan: (id: number) => client.delete(`/asr-optimization/plans/${id}`),
  deletePlanByHash: (configHash: string) => client.delete(`/asr-optimization/plans/by-hash/${encodeURIComponent(configHash)}`),
  exportFull: (data: { config_hash: string; dates?: string[] }) =>
    client.post('/asr-optimization/export-full', data, {
      responseType: 'blob',
      timeout: 300000,
    }),
  listFieldReviewMarks: (llmResultIds: number[]) =>
    client.get('/asr-optimization/field-review-marks', { params: { llm_result_ids: llmResultIds.join(',') } }),
  saveFieldReviewMark: (data: any) => client.post('/asr-optimization/field-review-marks', data),
  clearFieldReviewMark: (llmResultId: number, fieldGroup: string, fieldKey?: string) =>
    client.delete('/asr-optimization/field-review-marks', { params: { llm_result_id: llmResultId, field_group: fieldGroup, field_key: fieldKey } }),
}

// ========== ASR 文本转化评估 ==========
export const conversionEvalApi = {
  listRecords: (params?: any) => client.get('/conversion-eval/records', { params }),
  getRecord: (id: number) => client.get(`/conversion-eval/records/${id}`),
  getBusinessSegments: (id: number, textSource = 'raw') =>
    client.get(`/conversion-eval/records/${id}/business-segments`, { params: { text_source: textSource } }),
  getBusinessStructureCompare: (id: number) => client.get(`/conversion-eval/records/${id}/business-structure-compare`),
  listRuleCandidates: (params?: any) => client.get('/conversion-eval/rule-candidates', { params }),
  approveRuleCandidate: (data: any) => client.post('/conversion-eval/rule-candidates/approve', data),
  ignoreRuleCandidate: (data: any) => client.post('/conversion-eval/rule-candidates/ignore', data),
  createFromExam: (examRecordId: number, data: { asr_result_id?: number; converted_text?: string; conversion_version?: string } = {}) =>
    client.post(`/conversion-eval/records/from-exam/${examRecordId}`, data),
  batchCreateFromExams: (examRecordIds: number[], data: any = {}) =>
    client.post('/conversion-eval/records/batch-from-exams', { exam_record_ids: examRecordIds, ...data }),
  updateRecord: (id: number, data: any) => client.put(`/conversion-eval/records/${id}`, data),
  deleteRecord: (id: number) => client.delete(`/conversion-eval/records/${id}`),
  runConversion: (recordId: number) => client.post(`/conversion-eval/records/${recordId}/run-conversion`),
  batchRunConversion: (recordIds: number[]) => client.post('/conversion-eval/records/batch-run-conversion', { record_ids: recordIds }),
  addDetail: (recordId: number, data: any) => client.post(`/conversion-eval/records/${recordId}/details`, data),
  updateDetail: (detailId: number, data: any) => client.put(`/conversion-eval/details/${detailId}`, data),
  deleteDetail: (detailId: number) => client.delete(`/conversion-eval/details/${detailId}`),
  autoJudge: (recordId: number) => client.post(`/conversion-eval/records/${recordId}/auto-judge`),
  calculateMetrics: (recordId: number) => client.post(`/conversion-eval/records/${recordId}/calculate-metrics`),
  overview: () => client.get('/conversion-eval/stats/overview'),
  byCategory: () => client.get('/conversion-eval/stats/by-category'),
  highRisk: () => client.get('/conversion-eval/stats/high-risk'),
  // 批次评估工作台
  createBatch: (data: any) => client.post('/conversion-eval/batches', data),
  listBatches: () => client.get('/conversion-eval/batches'),
  getBatch: (id: number) => client.get(`/conversion-eval/batches/${id}`),
  getBatchStructureSummary: (id: number) => client.get(`/conversion-eval/batches/${id}/structure-summary`),
  deleteBatch: (id: number) => client.delete(`/conversion-eval/batches/${id}`),
  batchAutoJudge: (id: number) => client.post(`/conversion-eval/batches/${id}/auto-judge`),
  batchCalculateMetrics: (id: number) => client.post(`/conversion-eval/batches/${id}/calculate-metrics`),
}

// ========== ASR 转化配置 ==========
export const conversionConfigApi = {
  initDefaults: () => client.post('/conversion-config/init-defaults'),
  listVersions: () => client.get('/conversion-config/versions'),
  createVersion: (data: any) => client.post('/conversion-config/versions', data),
  updateVersion: (id: number, data: any) => client.put(`/conversion-config/versions/${id}`, data),
  cloneVersion: (id: number, data: any) => client.post(`/conversion-config/versions/${id}/clone`, data),
  publishVersion: (id: number) => client.post(`/conversion-config/versions/${id}/publish`),
  rollbackVersion: (id: number) => client.post(`/conversion-config/versions/${id}/rollback`),
  deleteVersion: (id: number) => client.delete(`/conversion-config/versions/${id}`),
  listLexicon: (versionId: number) => client.get(`/conversion-config/versions/${versionId}/lexicon`),
  createLexicon: (versionId: number, data: any) => client.post(`/conversion-config/versions/${versionId}/lexicon`, data),
  updateLexicon: (id: number, data: any) => client.put(`/conversion-config/lexicon/${id}`, data),
  deleteLexicon: (id: number) => client.delete(`/conversion-config/lexicon/${id}`),
  listRules: (versionId: number) => client.get(`/conversion-config/versions/${versionId}/rules`),
  createRule: (versionId: number, data: any) => client.post(`/conversion-config/versions/${versionId}/rules`, data),
  updateRule: (id: number, data: any) => client.put(`/conversion-config/rules/${id}`, data),
  deleteRule: (id: number) => client.delete(`/conversion-config/rules/${id}`),
  listBuiltinRules: () => client.get('/conversion-config/builtin-rules'),
  preview: (data: any) => client.post('/conversion-config/preview', data),
}

// ========== ASR 结构化处理流水线 ==========
export const conversionPipelineApi = {
  createExecution: (data: {
    source_type?: 'manual' | 'text_validation_run' | 'conversion_preview'
    source_id?: number
    input_source?: 'manual' | 'raw_asr_text' | 'corrected_text'
    text?: string
    scene?: string
    model_name?: string
    rule_version_id?: number
    run_mode?: 'create_only' | 'run_all'
  }) => client.post('/conversion-pipeline/executions', data, {
    timeout: 300000,
  }),

  batchCreateExecutions: (data: { source_ids: number[]; scene?: string; model_name?: string; rule_version_id?: number }) =>
    client.post('/conversion-pipeline/executions/batch', data, { timeout: 900000 }),

  getExecution: (id: number) =>
    client.get(`/conversion-pipeline/executions/${id}`),

  runStep: (id: number, stepCode: string) =>
    client.post(`/conversion-pipeline/executions/${id}/run-step`, {
      step_code: stepCode,
    }, {
      timeout: 300000,
    }),

  forkFromStep: (
    id: number,
    data: { step_code: string; rule_version_id?: number },
  ) =>
    client.post(`/conversion-pipeline/executions/${id}/fork-from-step`, data, {
      timeout: 300000,
    }),

  compare: (leftExecutionId: number, rightExecutionId: number) =>
    client.get('/conversion-pipeline/compare', {
      params: {
        left_execution_id: leftExecutionId,
        right_execution_id: rightExecutionId,
      },
    }),

  // ===== 以下为实施说明新增契约（后端并行实现，前端按契约对接）=====

  /** 最近执行记录（实施说明 §11.5）：source_type / source_id / rule_version_id / limit */
  listExecutions: (params?: {
    source_type?: string
    source_id?: number
    rule_version_id?: number
    limit?: number
  }) => client.get('/conversion-pipeline/executions', { params }),

  /** 执行到指定步骤（实施说明 §11.2）：从最近有效步骤执行到目标步骤后停止，返回完整执行 */
  runToStep: (id: number, stepCode: string) =>
    client.post(`/conversion-pipeline/executions/${id}/run-to-step`, {
      step_code: stepCode,
    }, {
      timeout: 300000,
    }),

  /** 保存步骤输出人工修改（实施说明 §11.3），返回 { step, invalidated_step_codes } */
  patchStepOutput: (
    id: number,
    stepCode: string,
    data: { manual_output_text: string; edit_note?: string },
  ) =>
    client.patch(`/conversion-pipeline/executions/${id}/steps/${stepCode}/output`, data, {
      timeout: 300000,
    }),

  /** 从下一步继续执行（实施说明 §11.4），返回完整执行 */
  continueExecution: (
    id: number,
    data: { from_step_code: string; run_mode?: 'run_all' | 'create_only' },
  ) =>
    client.post(`/conversion-pipeline/executions/${id}/continue`, data, {
      timeout: 300000,
    }),
}

// ========== ASR 文本验证 ==========
export const textValidationApi = {
  listRuns: (params?: any) => client.get('/text-validation/runs', { params }),
  getRun: (id: number) => client.get(`/text-validation/runs/${id}`),
  listCorrectionTemplates: () => client.get('/text-validation/correction-templates'),
  createCorrectionTemplate: (data: { name: string; content: string; is_default?: boolean }) =>
    client.post('/text-validation/correction-templates', data),
  updateCorrectionTemplate: (id: number, data: { name?: string; content?: string; is_default?: boolean; status?: string }) =>
    client.put(`/text-validation/correction-templates/${id}`, data),
  deleteCorrectionTemplate: (id: number) => client.delete(`/text-validation/correction-templates/${id}`),
  createRun: (data: {
    exam_record_id: number
    asr_result_id: number
    llm_model_id?: number
    prompt_template_id?: number
    correction_template_id?: number
    rule_version_id?: number
    rule_version?: string
    corrected_text_override?: string
  }) => client.post('/text-validation/runs', data, { timeout: 300000 }),
}

// ========== 测试执行 ==========
export const testApi = {
  runAsr: (recordId: string, asrModelId: number) =>
    client.get('/test/asr', { params: { record_id: recordId, asr_model_id: asrModelId }, timeout: 600000 }),
  runLlm: (data: { transcript: string; llm_model_id?: number; prompt_template: string }) =>
    client.post('/test/llm', data, { timeout: 300000 }),
  getHistory: (params?: any) => client.get('/test/history', { params }),
  getResult: (testId: number) => client.get(`/test/${testId}`),
  updateEval: (testId: number, data: any) => client.put(`/test/${testId}/evaluate`, data),
  // LLM 历史记录 (跨患者)
  getLlmHistory: (params?: any) => client.get('/test/llm-history', { params }),
  exportLlmHistory: (params?: any) => {
    const qs = new URLSearchParams()
    if (params) for (const [k, v] of Object.entries(params)) if (v) qs.set(k, String(v))
    return `${API_BASE}/test/llm-history/export?${qs.toString()}`
  },
}

/**
 * ASR 流式转写 (SSE)
 * @param data 参数
 * @param callbacks 回调: onProgress / onSegment / onComplete / onError
 * @returns close(): 主动关闭连接的函数
 *
 * 服务端事件:
 * - progress: { stage, seg_index, total }
 * - segment:  { stage, seg_index, text, duration }
 * - complete: { stage, segments, full_transcript }
 * - error:    { stage, message }
 */
export function startAsrSSE(
  data: { record_id: string; asr_model_id: number; hotwords?: string },
  callbacks: {
    onProgress?: (info: { seg_index: number; total: number }) => void
    onSegment?: (info: { seg_index: number; text: string; duration: number }) => void
    onComplete?: (info: { segments: any[]; full_transcript: string }) => void
    onError?: (message: string) => void
  } = {},
): () => void {
  const params = new URLSearchParams()
  params.set('record_id', data.record_id)
  params.set('asr_model_id', String(data.asr_model_id))
  if (data.hotwords) params.set('hotwords', data.hotwords)

  const url = `${API_BASE}/test/asr/stream?${params.toString()}`
  const es = new EventSource(url)

  es.addEventListener('progress', (ev: MessageEvent) => {
    try {
      const parsed = JSON.parse(ev.data)
      callbacks.onProgress?.({ seg_index: parsed.seg_index, total: parsed.total })
    } catch { /* ignore */ }
  })

  es.addEventListener('segment', (ev: MessageEvent) => {
    try {
      const parsed = JSON.parse(ev.data)
      callbacks.onSegment?.({ seg_index: parsed.seg_index, text: parsed.text, duration: parsed.duration })
    } catch { /* ignore */ }
  })

  es.addEventListener('complete', (ev: MessageEvent) => {
    try {
      const parsed = JSON.parse(ev.data)
      callbacks.onComplete?.({ segments: parsed.segments, full_transcript: parsed.full_transcript })
    } catch { /* ignore */ }
    es.close()
  })

  es.addEventListener('error', (ev: MessageEvent) => {
    // FastAPI SSE 的 error 事件可能是服务端主动发的错误, 也可能是连接断开
    try {
      // MessageEvent.data 只在有 data 字段时存在 ; Event (无 type) 的 ev 走这里
      if (ev.data) {
        const parsed = JSON.parse(ev.data)
        callbacks.onError?.(parsed.message || 'ASR 流式请求失败')
      } else {
        // 无 data 的 error event 通常是连接问题, 不重复通知
      }
    } catch {
      // ignore
    }
    es.close()
  })

  // 返回主动关闭函数
  return () => es.close()
}

// SSE 测试执行 (ASR+LLM 完整链路)
export function startTestSSE(data: {
  record_id: string
  asr_model_id: number
  llm_model_id?: number
  prompt_version?: string
}): EventSource {
  const params = new URLSearchParams()
  params.set('record_id', data.record_id)
  params.set('asr_model_id', String(data.asr_model_id))
  if (data.llm_model_id) params.set('llm_model_id', String(data.llm_model_id))
  if (data.prompt_version) params.set('prompt_version', data.prompt_version)

  const url = `${API_BASE}/test/start?${params.toString()}`
  return new EventSource(url)
}

// ========== 提示词模版 ==========
export const promptTemplateApi = {
  list: () => client.get('/prompt-templates'),
  get: (id: number) => client.get(`/prompt-templates/${id}`),
  create: (data: { name: string; content: string; is_default?: boolean }) =>
    client.post('/prompt-templates', data),
  update: (id: number, data: { name?: string; content?: string; is_default?: boolean }) =>
    client.put(`/prompt-templates/${id}`, data),
  delete: (id: number) => client.delete(`/prompt-templates/${id}`),
  initDefaults: () => client.post('/prompt-templates/init-defaults'),
}

// ========== 患者级 ASR/LLM 持久化结果 ==========
export const patientApi = {
  startAsrTask(patientId: number, data: {
    asr_model_id: number
    hotwords?: string
    variant_name?: string
    params_override?: any
    source?: string
    experiment_key?: string
    config_hash?: string
  }) {
    return client.post(`/patients/${patientId}/asr/tasks`, data, { timeout: 30000 })
  },
  getAsrTask(patientId: number, resultId: number) {
    return client.get(`/patients/${patientId}/asr/tasks/${resultId}`, { timeout: 30000 })
  },
  repairAsrMissingSegments(patientId: number, resultId: number) {
    return client.post(`/patients/${patientId}/asr-results/${resultId}/repair-missing-segments`, {}, { timeout: 900000 })
  },
  runAsrSSE(patientId: number, asrModelId: number, hotwords?: string, extra?: { variant_name?: string; params_override?: any; source?: string; experiment_key?: string; config_hash?: string }): EventSource {
    const params = new URLSearchParams()
    params.set('asr_model_id', String(asrModelId))
    if (hotwords) params.set('hotwords', hotwords)
    if (extra?.variant_name) params.set('variant_name', extra.variant_name)
    if (extra?.params_override) params.set('params_override', JSON.stringify(extra.params_override))
    if (extra?.source) params.set('source', extra.source)
    if (extra?.experiment_key) params.set('experiment_key', extra.experiment_key)
    if (extra?.config_hash) params.set('config_hash', extra.config_hash)
    return new EventSource(`${API_BASE}/patients/${patientId}/asr/stream?${params.toString()}`)
  },
  listAsrResults: (patientId: number) => client.get(`/patients/${patientId}/asr-results`),
  listAsrResultsBatch: (patientIds: number[]) =>
    client.get('/patients/asr-results/batch', {
      params: { patient_ids: patientIds.join(',') },
      timeout: 120000,
    }),
  getAsrReference: (patientId: number) => client.get(`/patients/${patientId}/asr-reference`),
  listAsrReferencesBatch: (patientIds: number[]) =>
    client.get('/patients/asr-references/batch', {
      params: { patient_ids: patientIds.join(',') },
      timeout: 120000,
    }),
  saveAsrReference: (patientId: number, data: { base_asr_result_id?: number; reference_text: string; reference_annotations?: any[]; note?: string }) =>
    client.put(`/patients/${patientId}/asr-reference`, data),
  getAsrCurrent: (patientId: number) => client.get(`/patients/${patientId}/asr-current`),
  setAsrCurrent: (patientId: number, resultId: number) =>
    client.put(`/patients/${patientId}/asr-results/${resultId}/current`),
  runLlm: (patientId: number, data: {
    llm_model_id: number
    asr_result_id?: number
    prompt_content?: string
    prompt_template_id?: number
    source?: string
    experiment_key?: string
  }) => client.post(`/patients/${patientId}/llm/run`, data, { timeout: 300000 }),
  listLlmResults: (patientId: number, params?: { include_optimization?: boolean }) =>
    client.get(`/patients/${patientId}/llm-results`, { params }),
  getLlmCurrent: (patientId: number) => client.get(`/patients/${patientId}/llm-current`),
  setLlmCurrent: (patientId: number, resultId: number) =>
    client.put(`/patients/${patientId}/llm-results/${resultId}/current`),
  // 字段人工标记
  saveFieldReviewMark: (patientId: number, data: any) => client.post(`/patients/${patientId}/field-review-marks`, data),
  clearFieldReviewMark: (patientId: number, fieldGroup: string) => client.delete(`/patients/${patientId}/field-review-marks`, { params: { field_group: fieldGroup } }),
  exportLlmResults: (patientId: number) => `${API_BASE}/patients/${patientId}/llm-results/export`,
  clearLlmResults: (patientId: number) => client.delete(`/patients/${patientId}/llm-results`),
}

export default client
