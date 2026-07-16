/**
 * API 客户端封装
 */
import axios, { AxiosInstance } from 'axios'
import { message } from 'ant-design-vue'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

const client: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const msg = error.response?.data?.detail || error.message || '请求失败'
    message.error(msg)
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
  runAsrSSE(patientId: number, asrModelId: number, hotwords?: string): EventSource {
    const params = new URLSearchParams()
    params.set('asr_model_id', String(asrModelId))
    if (hotwords) params.set('hotwords', hotwords)
    return new EventSource(`${API_BASE}/patients/${patientId}/asr/stream?${params.toString()}`)
  },
  listAsrResults: (patientId: number) => client.get(`/patients/${patientId}/asr-results`),
  listAsrResultsBatch: (patientIds: number[]) =>
    client.get('/patients/asr-results/batch', {
      params: { patient_ids: patientIds.join(',') },
      timeout: 120000,
    }),
  getAsrCurrent: (patientId: number) => client.get(`/patients/${patientId}/asr-current`),
  setAsrCurrent: (patientId: number, resultId: number) =>
    client.put(`/patients/${patientId}/asr-results/${resultId}/current`),
  runLlm: (patientId: number, data: {
    llm_model_id: number
    asr_result_id?: number
    prompt_content?: string
    prompt_template_id?: number
  }) => client.post(`/patients/${patientId}/llm/run`, data, { timeout: 300000 }),
  listLlmResults: (patientId: number) => client.get(`/patients/${patientId}/llm-results`),
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
